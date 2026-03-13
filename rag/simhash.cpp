// simhash.cpp — high-performance SimHash-64 + helpers via pybind11
// Implements the same algorithm as dedup_docs_jsonl.py:
//   tokenize (CJK single chars + ASCII words) → Counter →
//   per-token SHA-1[:8] → 64-bit weighted bit accumulator → fingerprint
//
// Also exposes:
//   hamming_distance(a, b) → int
//   band_keys(fp, bands)   → List[(int,int)]
//   sha1_text(text)        → hex str  (same as Python sha1_text)
//   DedupEngine            → stateful dedup engine (exact + near-dup via LSH)
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <openssl/evp.h>
#include <openssl/sha.h>

#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <tuple>
#include <stdexcept>

namespace py = pybind11;

// ── SHA-1 helper ─────────────────────────────────────────────────────────────

static void sha1_bytes(const char* data, std::size_t len, unsigned char out[20]) {
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    EVP_DigestInit_ex(ctx, EVP_sha1(), nullptr);
    EVP_DigestUpdate(ctx, data, len);
    unsigned int outlen = 20;
    EVP_DigestFinal_ex(ctx, out, &outlen);
    EVP_MD_CTX_free(ctx);
}

static std::string sha1_hex(const std::string& s) {
    unsigned char digest[20];
    sha1_bytes(s.data(), s.size(), digest);
    char hex[41];
    for (int i = 0; i < 20; i++) {
        snprintf(hex + i * 2, 3, "%02x", digest[i]);
    }
    return std::string(hex, 40);
}

// ── Tokenizer ─────────────────────────────────────────────────────────────────
// Matches Python:  TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")
// Input is UTF-8.

static std::vector<std::string> tokenize(const std::string& text) {
    std::vector<std::string> tokens;
    const unsigned char* p = reinterpret_cast<const unsigned char*>(text.data());
    const unsigned char* end = p + text.size();

    while (p < end) {
        unsigned char b = *p;

        if (b < 0x80) {
            // ASCII
            char c = static_cast<char>(b);
            if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                (c >= '0' && c <= '9') || c == '_') {
                // collect ASCII word
                const unsigned char* start = p;
                while (p < end) {
                    char cc = static_cast<char>(*p);
                    if ((cc >= 'A' && cc <= 'Z') || (cc >= 'a' && cc <= 'z') ||
                        (cc >= '0' && cc <= '9') || cc == '_') {
                        ++p;
                    } else {
                        break;
                    }
                }
                // lowercase
                std::string tok(reinterpret_cast<const char*>(start), p - start);
                for (char& ch : tok) {
                    if (ch >= 'A' && ch <= 'Z') ch += 32;
                }
                tokens.push_back(std::move(tok));
            } else {
                ++p;
            }
        } else if ((b & 0xE0) == 0xC0) {
            // 2-byte UTF-8
            p += 2;
        } else if ((b & 0xF0) == 0xE0) {
            // 3-byte UTF-8: potentially CJK U+4E00..U+9FFF
            if (p + 2 < end) {
                uint32_t cp = ((uint32_t)(b & 0x0F) << 12) |
                              ((uint32_t)(p[1] & 0x3F) << 6) |
                              ((uint32_t)(p[2] & 0x3F));
                if (cp >= 0x4E00 && cp <= 0x9FFF) {
                    // single CJK char token (3 bytes)
                    tokens.emplace_back(reinterpret_cast<const char*>(p), 3);
                }
            }
            p += 3;
        } else if ((b & 0xF8) == 0xF0) {
            // 4-byte UTF-8
            p += 4;
        } else {
            ++p;
        }
    }
    return tokens;
}

// ── SimHash-64 ────────────────────────────────────────────────────────────────

static uint64_t simhash64(const std::string& text) {
    auto tokens = tokenize(text);
    if (tokens.empty()) return 0;

    // count token frequencies
    std::unordered_map<std::string, int> weights;
    weights.reserve(tokens.size());
    for (const auto& t : tokens) ++weights[t];

    // accumulate 64-bit vector
    int64_t vec[64] = {};

    for (const auto& [tok, w] : weights) {
        unsigned char digest[20];
        sha1_bytes(tok.data(), tok.size(), digest);
        // take first 8 bytes as big-endian uint64
        uint64_t h = 0;
        for (int i = 0; i < 8; i++) {
            h = (h << 8) | digest[i];
        }
        for (int i = 0; i < 64; i++) {
            if ((h >> i) & 1ULL)
                vec[i] += w;
            else
                vec[i] -= w;
        }
    }

    uint64_t out = 0;
    for (int i = 0; i < 64; i++) {
        if (vec[i] >= 0) out |= (1ULL << i);
    }
    return out;
}

// ── Hamming distance ──────────────────────────────────────────────────────────

static int hamming_distance(uint64_t a, uint64_t b) {
    return __builtin_popcountll(a ^ b);
}

// ── Band keys (LSH) ───────────────────────────────────────────────────────────

static std::vector<std::pair<int, uint64_t>> band_keys(uint64_t fp, int bands) {
    if (bands <= 0 || 64 % bands != 0)
        throw std::invalid_argument("bands must be a positive divisor of 64");
    int width = 64 / bands;
    uint64_t mask = (1ULL << width) - 1;
    std::vector<std::pair<int, uint64_t>> keys;
    keys.reserve(bands);
    for (int b = 0; b < bands; b++) {
        keys.emplace_back(b, (fp >> (b * width)) & mask);
    }
    return keys;
}

// ── DedupEngine ───────────────────────────────────────────────────────────────
// Stateful dedup engine holding all mutable per-run state.
// Replaces the Python-level seen_sha1 / kept_fp / buckets data structures.
// Each call to process() returns a tuple:
//   ("keep",  assigned_doc_id, text_hash, -1)
//   ("exact", "",              canonical_sha1, -1)
//   ("near",  canonical_doc_id, canonical_sha1, dist)

struct BucketKey {
    int   band;
    uint64_t val;
    bool operator==(const BucketKey& o) const noexcept {
        return band == o.band && val == o.val;
    }
};
struct BucketKeyHash {
    std::size_t operator()(const BucketKey& k) const noexcept {
        // Mix band index into high bits.
        return std::hash<uint64_t>()((static_cast<uint64_t>(k.band) << 56) ^ k.val);
    }
};

struct SweepState {
    std::unordered_set<std::string> seen_sha1;
    std::vector<uint64_t> kept_fp;
    std::unordered_map<BucketKey, std::vector<int>, BucketKeyHash> buckets;
    std::map<int, int> near_dist;
    std::size_t kept = 0;
    std::size_t exact_dup = 0;
    std::size_t near_dup = 0;

    void reserve(std::size_t n, int bands) {
        seen_sha1.reserve(n);
        kept_fp.reserve(n);
        buckets.reserve(n * bands);
    }
};

class DedupEngine {
    std::unordered_set<std::string> seen_sha1_;
    std::vector<std::string>        kept_doc_ids_;
    std::vector<std::string>        kept_sha1_;
    std::vector<uint64_t>           kept_fp_;
    std::unordered_map<BucketKey, std::vector<int>, BucketKeyHash> buckets_;

    int bands_;
    int threshold_;

    std::vector<BucketKey> make_keys(uint64_t fp) const {
        int width = 64 / bands_;
        uint64_t mask = (1ULL << width) - 1;
        std::vector<BucketKey> keys;
        keys.reserve(bands_);
        for (int b = 0; b < bands_; b++) {
            keys.push_back({b, (fp >> (b * width)) & mask});
        }
        return keys;
    }

public:
    DedupEngine(int bands, int threshold) : bands_(bands), threshold_(threshold) {
        if (bands <= 0 || 64 % bands != 0)
            throw std::invalid_argument("bands must be a positive divisor of 64");
    }

    // Returns (status, doc_id_or_canonical, canonical_sha1, distance_or_-1)
    std::tuple<std::string, std::string, std::string, int>
    process(uint64_t fp, const std::string& text_hash, const std::string& doc_id_hint) {
        // 1. Exact duplicate
        if (seen_sha1_.count(text_hash)) {
            return {"exact", std::string(), text_hash, -1};
        }

        // 2. Near-duplicate via LSH bands
        auto keys = make_keys(fp);
        std::unordered_set<int> candidates;
        for (const auto& key : keys) {
            auto it = buckets_.find(key);
            if (it != buckets_.end()) {
                for (int idx : it->second) {
                    candidates.insert(idx);
                }
            }
        }

        for (int idx : candidates) {
            int dist = hamming_distance(fp, kept_fp_[idx]);
            if (dist <= threshold_) {
                return {"near", kept_doc_ids_[idx], kept_sha1_[idx], dist};
            }
        }

        // 3. Keep — update state
        std::string doc_id = doc_id_hint;
        if (doc_id.empty()) {
            doc_id = "doc_" + std::to_string(kept_fp_.size());
        }

        seen_sha1_.insert(text_hash);
        int new_idx = static_cast<int>(kept_fp_.size());
        kept_doc_ids_.push_back(doc_id);
        kept_sha1_.push_back(text_hash);
        kept_fp_.push_back(fp);
        for (const auto& key : keys) {
            buckets_[key].push_back(new_idx);
        }

        return {"keep", doc_id, text_hash, -1};
    }

    std::vector<std::tuple<std::string, std::string, std::string, int>>
    process_batch(
        const std::vector<uint64_t>& fps,
        const std::vector<std::string>& text_hashes,
        const std::vector<std::string>& doc_id_hints
    ) {
        if (fps.size() != text_hashes.size()) {
            throw std::invalid_argument("fps and text_hashes must have the same length");
        }
        if (!doc_id_hints.empty() && doc_id_hints.size() != fps.size()) {
            throw std::invalid_argument("doc_id_hints must be empty or same length as fps");
        }

        std::vector<std::tuple<std::string, std::string, std::string, int>> out;
        out.reserve(fps.size());
        for (std::size_t i = 0; i < fps.size(); i++) {
            const std::string& hint = doc_id_hints.empty() ? std::string() : doc_id_hints[i];
            out.push_back(process(fps[i], text_hashes[i], hint));
        }
        return out;
    }

    std::size_t size() const noexcept { return kept_fp_.size(); }

    void reserve(std::size_t n) {
        seen_sha1_.reserve(n);
        kept_doc_ids_.reserve(n);
        kept_sha1_.reserve(n);
        kept_fp_.reserve(n);
        buckets_.reserve(n * bands_);
    }
};

class ThresholdSweepEngine {
    std::vector<int> thresholds_;
    int bands_;
    std::vector<SweepState> states_;

    std::vector<BucketKey> make_keys(uint64_t fp) const {
        int width = 64 / bands_;
        uint64_t mask = (1ULL << width) - 1;
        std::vector<BucketKey> keys;
        keys.reserve(bands_);
        for (int b = 0; b < bands_; b++) {
            keys.push_back({b, (fp >> (b * width)) & mask});
        }
        return keys;
    }

public:
    ThresholdSweepEngine(const std::vector<int>& thresholds, int bands)
        : thresholds_(thresholds), bands_(bands) {
        if (bands <= 0 || 64 % bands != 0) {
            throw std::invalid_argument("bands must be a positive divisor of 64");
        }
        if (thresholds_.empty()) {
            throw std::invalid_argument("thresholds must not be empty");
        }
        for (int t : thresholds_) {
            if (t < 0) {
                throw std::invalid_argument("thresholds must be >= 0");
            }
        }
        states_.resize(thresholds_.size());
    }

    void process(uint64_t fp, const std::string& text_hash) {
        auto keys = make_keys(fp);

        for (std::size_t i = 0; i < thresholds_.size(); i++) {
            int threshold = thresholds_[i];
            SweepState& st = states_[i];

            if (st.seen_sha1.count(text_hash)) {
                st.exact_dup += 1;
                continue;
            }

            std::unordered_set<int> candidates;
            for (const auto& key : keys) {
                auto it = st.buckets.find(key);
                if (it == st.buckets.end()) {
                    continue;
                }
                for (int idx : it->second) {
                    candidates.insert(idx);
                }
            }

            bool is_near = false;
            int best_dist = -1;
            for (int idx : candidates) {
                int dist = hamming_distance(fp, st.kept_fp[idx]);
                if (best_dist < 0 || dist < best_dist) {
                    best_dist = dist;
                }
                if (dist <= threshold) {
                    is_near = true;
                    break;
                }
            }

            if (is_near) {
                st.near_dup += 1;
                if (best_dist >= 0) {
                    st.near_dist[best_dist] += 1;
                }
                continue;
            }

            int keep_idx = static_cast<int>(st.kept_fp.size());
            st.seen_sha1.insert(text_hash);
            st.kept_fp.push_back(fp);
            for (const auto& key : keys) {
                st.buckets[key].push_back(keep_idx);
            }
            st.kept += 1;
        }
    }

    void process_batch(const std::vector<uint64_t>& fps,
                       const std::vector<std::string>& text_hashes) {
        if (fps.size() != text_hashes.size()) {
            throw std::invalid_argument("fps and text_hashes must have the same length");
        }
        for (std::size_t i = 0; i < fps.size(); i++) {
            process(fps[i], text_hashes[i]);
        }
    }

    py::list snapshot() const {
        py::list out;
        for (std::size_t i = 0; i < thresholds_.size(); i++) {
            const SweepState& st = states_[i];
            py::dict row;
            row["threshold"] = thresholds_[i];
            row["kept"] = py::int_(st.kept);
            row["exact_dup"] = py::int_(st.exact_dup);
            row["near_dup"] = py::int_(st.near_dup);

            py::dict near_dist;
            for (const auto& [dist, count] : st.near_dist) {
                near_dist[py::str(std::to_string(dist))] = py::int_(count);
            }
            row["near_distance_distribution"] = near_dist;
            out.append(row);
        }
        return out;
    }

    void reserve(std::size_t n) {
        for (auto& st : states_) {
            st.reserve(n, bands_);
        }
    }
};

PYBIND11_MODULE(_simhash, m) {
    m.doc() = "High-performance SimHash-64 + DedupEngine (C++ + OpenSSL)";

    m.def("simhash64", [](const std::string& text) -> uint64_t {
        return simhash64(text);
    }, py::arg("text"),
    "Compute 64-bit SimHash fingerprint of text (UTF-8).");

    m.def("simhash64_worker", [](const std::string& text) -> uint64_t {
        return simhash64(text);
    }, py::arg("text"),
    "Alias for simhash64 (drop-in for ProcessPoolExecutor worker).");

    m.def("hamming_distance", [](uint64_t a, uint64_t b) -> int {
        return hamming_distance(a, b);
    }, py::arg("a"), py::arg("b"),
    "Compute Hamming distance between two 64-bit fingerprints.");

    m.def("band_keys", [](uint64_t fp, int bands)
          -> std::vector<std::pair<int, uint64_t>> {
        return band_keys(fp, bands);
    }, py::arg("fp"), py::arg("bands"),
    "Return LSH band keys for fingerprint.");

    m.def("sha1_text", [](const std::string& s) -> std::string {
        return sha1_hex(s);
    }, py::arg("text"),
    "Return hex SHA-1 digest of UTF-8 text.");

    m.def("tokenize", [](const std::string& text) -> std::vector<std::string> {
        return tokenize(text);
    }, py::arg("text"),
    "Tokenize text into CJK single chars + ASCII words (lowercased).");

    py::class_<DedupEngine>(m, "DedupEngine")
        .def(py::init<int, int>(), py::arg("bands"), py::arg("threshold"),
             "Create a DedupEngine.\n"
             "  bands     – number of LSH bands (must divide 64)\n"
             "  threshold – max Hamming distance for near-dup")
        .def("process",
             &DedupEngine::process,
             py::arg("fp"), py::arg("text_hash"), py::arg("doc_id_hint") = "",
             "Process one document fingerprint.\n"
             "Returns (status, doc_id, sha1, dist) where status is "
             "'keep', 'exact', or 'near'.")
           .def("process_batch",
               &DedupEngine::process_batch,
               py::arg("fps"), py::arg("text_hashes"),
               py::arg("doc_id_hints") = std::vector<std::string>{},
               "Process a batch of document fingerprints.\n"
               "Returns a list of (status, doc_id, sha1, dist) tuples.")
        .def("reserve", &DedupEngine::reserve, py::arg("n"),
             "Pre-allocate internal hash tables for n documents.")
        .def("__len__", &DedupEngine::size,
             "Number of kept (non-duplicate) documents.");

        py::class_<ThresholdSweepEngine>(m, "ThresholdSweepEngine")
           .def(py::init<const std::vector<int>&, int>(),
               py::arg("thresholds"), py::arg("bands"),
               "Create a multi-threshold SimHash sweep engine.\n"
               "  thresholds – list of Hamming-distance thresholds to compare\n"
               "  bands      – number of LSH bands (must divide 64)")
           .def("process",
               &ThresholdSweepEngine::process,
               py::arg("fp"), py::arg("text_hash"),
               "Process one fingerprint + SHA-1 text hash across all thresholds.")
           .def("process_batch",
               &ThresholdSweepEngine::process_batch,
               py::arg("fps"), py::arg("text_hashes"),
               "Process a batch of fingerprints + SHA-1 text hashes across all thresholds.")
           .def("snapshot",
               &ThresholdSweepEngine::snapshot,
               "Return current per-threshold stats as a list of dicts.")
           .def("reserve",
               &ThresholdSweepEngine::reserve,
               py::arg("n"),
               "Pre-allocate internal hash tables for n documents per threshold.");
}
