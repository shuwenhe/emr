// simhash.cpp — high-performance SimHash-64 + helpers via pybind11
// Implements the same algorithm as dedup_docs_jsonl.py:
//   tokenize (CJK single chars + ASCII words) → Counter →
//   per-token SHA-1[:8] → 64-bit weighted bit accumulator → fingerprint
//
// Also exposes:
//   hamming_distance(a, b) → int
//   band_keys(fp, bands)   → List[(int,int)]
//   sha1_text(text)        → hex str  (same as Python sha1_text)
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <openssl/evp.h>
#include <openssl/sha.h>

#include <cstdint>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>
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

// ── pybind11 module ───────────────────────────────────────────────────────────

PYBIND11_MODULE(_simhash, m) {
    m.doc() = "High-performance SimHash-64 (C++ + OpenSSL)";

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
}
