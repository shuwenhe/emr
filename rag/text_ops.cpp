#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <regex>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

struct CpPos {
    uint32_t cp;
    std::size_t byte_pos;
    std::size_t byte_len;
};

static bool decode_one(const std::string& s, std::size_t i, CpPos& out) {
    if (i >= s.size()) {
        return false;
    }
    const unsigned char* p = reinterpret_cast<const unsigned char*>(s.data());
    unsigned char b = p[i];
    out.byte_pos = i;

    if (b < 0x80) {
        out.cp = b;
        out.byte_len = 1;
        return true;
    }
    if ((b & 0xE0) == 0xC0 && i + 1 < s.size()) {
        out.cp = ((uint32_t)(b & 0x1F) << 6) | (uint32_t)(p[i + 1] & 0x3F);
        out.byte_len = 2;
        return true;
    }
    if ((b & 0xF0) == 0xE0 && i + 2 < s.size()) {
        out.cp = ((uint32_t)(b & 0x0F) << 12) |
                 ((uint32_t)(p[i + 1] & 0x3F) << 6) |
                 (uint32_t)(p[i + 2] & 0x3F);
        out.byte_len = 3;
        return true;
    }
    if ((b & 0xF8) == 0xF0 && i + 3 < s.size()) {
        out.cp = ((uint32_t)(b & 0x07) << 18) |
                 ((uint32_t)(p[i + 1] & 0x3F) << 12) |
                 ((uint32_t)(p[i + 2] & 0x3F) << 6) |
                 (uint32_t)(p[i + 3] & 0x3F);
        out.byte_len = 4;
        return true;
    }

    out.cp = b;
    out.byte_len = 1;
    return true;
}

static std::vector<CpPos> decode_all(const std::string& s) {
    std::vector<CpPos> out;
    out.reserve(s.size());
    std::size_t i = 0;
    while (i < s.size()) {
        CpPos c{};
        decode_one(s, i, c);
        out.push_back(c);
        i += c.byte_len;
    }
    return out;
}

static std::size_t cp_len(const std::string& s) {
    return decode_all(s).size();
}

static bool is_space_cp(uint32_t cp) {
    if (cp <= 0x20) {
        return true;
    }
    return cp == 0x3000 || cp == 0x00A0;
}

static std::string trim_spaces(const std::string& s) {
    auto cps = decode_all(s);
    if (cps.empty()) {
        return "";
    }
    std::size_t left = 0;
    while (left < cps.size() && is_space_cp(cps[left].cp)) {
        left++;
    }
    if (left >= cps.size()) {
        return "";
    }
    std::size_t right = cps.size();
    while (right > left && is_space_cp(cps[right - 1].cp)) {
        right--;
    }
    std::size_t start = cps[left].byte_pos;
    std::size_t end = cps[right - 1].byte_pos + cps[right - 1].byte_len;
    return s.substr(start, end - start);
}

static std::string collapse_spaces(const std::string& s) {
    auto cps = decode_all(s);
    std::string out;
    out.reserve(s.size());
    bool in_space = false;
    for (const auto& c : cps) {
        uint32_t cp = c.cp;
        if (cp == 0x3000 || cp == 0x00A0) {
            cp = 0x20;
        }
        if ((cp <= 0x08) || cp == 0x0B || cp == 0x0C || (cp >= 0x0E && cp <= 0x1F) || cp == 0x7F) {
            cp = 0x20;
        }
        if (cp == 0x20) {
            if (!in_space) {
                out.push_back(' ');
                in_space = true;
            }
            continue;
        }
        in_space = false;
        out.append(s, c.byte_pos, c.byte_len);
    }
    return trim_spaces(out);
}

static bool is_cjk_unified(uint32_t cp) {
    return cp >= 0x4E00 && cp <= 0x9FFF;
}

static bool is_ascii_word(uint32_t cp) {
    return (cp >= '0' && cp <= '9') ||
           (cp >= 'A' && cp <= 'Z') ||
           (cp >= 'a' && cp <= 'z');
}

static bool contains_any(const std::string& s, const std::vector<std::string>& needles) {
    for (const auto& n : needles) {
        if (!n.empty() && s.find(n) != std::string::npos) {
            return true;
        }
    }
    return false;
}

static int count_page_refs(const std::vector<CpPos>& cps) {
    int count = 0;
    for (std::size_t i = 0; i < cps.size(); i++) {
        uint32_t open = cps[i].cp;
        if (open != '(' && open != 0xFF08) {
            continue;
        }
        std::size_t j = i + 1;
        while (j < cps.size() && is_space_cp(cps[j].cp)) {
            j++;
        }
        int digits = 0;
        while (j < cps.size() && cps[j].cp >= '0' && cps[j].cp <= '9' && digits < 5) {
            digits++;
            j++;
        }
        while (j < cps.size() && is_space_cp(cps[j].cp)) {
            j++;
        }
        if (digits >= 1 && digits <= 4 && j < cps.size() && (cps[j].cp == ')' || cps[j].cp == 0xFF09)) {
            count++;
            i = j;
        }
    }
    return count;
}

static int count_enum_markers(const std::vector<CpPos>& cps) {
    int count = 0;
    auto is_cn_num = [](uint32_t cp) {
        return cp == 0x4E00 || cp == 0x4E8C || cp == 0x4E09 || cp == 0x56DB || cp == 0x4E94 ||
               cp == 0x516D || cp == 0x4E03 || cp == 0x516B || cp == 0x4E5D || cp == 0x5341;
    };
    for (std::size_t i = 0; i < cps.size(); i++) {
        if (!(cps[i].cp >= '0' && cps[i].cp <= '9') && !is_cn_num(cps[i].cp)) {
            continue;
        }
        std::size_t j = i;
        int span = 0;
        while (j < cps.size() && span < 6) {
            uint32_t cp = cps[j].cp;
            if ((cp >= '0' && cp <= '9') || is_cn_num(cp)) {
                j++;
                span++;
                continue;
            }
            break;
        }
        if (j < cps.size()) {
            uint32_t m = cps[j].cp;
            if (m == 0x3001 || m == '.' || m == 0xFF0E || m == ':' || m == 0xFF1A || m == ')') {
                count++;
                i = j;
            }
        }
    }
    return count;
}

static int count_page_noise(const std::vector<CpPos>& cps) {
    auto is_sep = [](uint32_t cp) {
        return is_space_cp(cp) || cp == '/' || cp == '.' || cp == '-' || cp == '_' || cp == 0x00B7;
    };
    int count = 0;
    for (std::size_t i = 0; i < cps.size(); i++) {
        if (!(cps[i].cp >= '0' && cps[i].cp <= '9')) {
            continue;
        }
        std::size_t left = i;
        std::size_t right = i;
        while (right < cps.size() && cps[right].cp >= '0' && cps[right].cp <= '9') {
            right++;
        }
        int digits = (int)(right - left);
        uint32_t lcp = left == 0 ? 0 : cps[left - 1].cp;
        uint32_t rcp = right >= cps.size() ? 0 : cps[right].cp;
        if (digits >= 1 && digits <= 4 && (left == 0 || is_sep(lcp)) && (right >= cps.size() || is_sep(rcp))) {
            count++;
            i = right;
        }
    }
    return count;
}

static std::string lower_ascii_copy(const std::string& s) {
    std::string out = s;
    for (char& ch : out) {
        unsigned char u = static_cast<unsigned char>(ch);
        if (u >= 'A' && u <= 'Z') {
            ch = static_cast<char>(u + 32);
        }
    }
    return out;
}

static bool has_email_pattern(const std::string& s) {
    std::size_t at = s.find('@');
    if (at == std::string::npos || at == 0 || at + 1 >= s.size()) {
        return false;
    }
    std::size_t dot = s.find('.', at + 1);
    return dot != std::string::npos && dot + 1 < s.size();
}

static bool is_low_signal_text_cpp(const std::string& text) {
    std::string normalized = collapse_spaces(text);
    if (normalized.empty()) {
        return true;
    }

    auto cps = decode_all(normalized);
    int useful = 0;
    int symbols = 0;
    for (const auto& c : cps) {
        if (is_ascii_word(c.cp) || is_cjk_unified(c.cp)) {
            useful++;
        }
        if (c.cp == 0x00B7 || c.cp == '.' || c.cp == '/' || c.cp == '\\' || c.cp == '-' || c.cp == '_' ||
            c.cp == '+' || c.cp == '*' || c.cp == '=' || c.cp == '~' || c.cp == ':' || c.cp == 0xFF1A ||
            c.cp == '(' || c.cp == ')' || c.cp == 0xFF08 || c.cp == 0xFF09) {
            symbols++;
        }
    }

    double useful_ratio = static_cast<double>(useful) / std::max<std::size_t>(1, cps.size());
    double symbol_ratio = static_cast<double>(symbols) / std::max<std::size_t>(1, cps.size());

    bool has_dot_leader = contains_any(text, {"...", "···", "•••", "‧‧‧", "⋯", "…"});
    int page_refs = count_page_refs(cps);
    int enum_refs = count_enum_markers(cps);
    int page_noise = count_page_noise(cps);
    int item_markers = enum_refs;

    bool toc_hint = (normalized.find("目录") != std::string::npos) ||
                    (normalized.find("目 录") != std::string::npos) ||
                    (normalized.find("第") != std::string::npos && normalized.find("章") != std::string::npos);

    bool has_email = has_email_pattern(lower_ascii_copy(normalized));
    int n = static_cast<int>(cps.size());

    if (n <= 120 && has_dot_leader && useful_ratio < 0.62) {
        return true;
    }
    if (n <= 160 && has_dot_leader && page_refs >= 1 && enum_refs >= 1 && useful_ratio < 0.68) {
        return true;
    }
    if (n <= 90 && toc_hint && page_noise >= 1) {
        return true;
    }
    if (n <= 110 && page_noise >= 2 && enum_refs >= 1 && symbol_ratio >= 0.12) {
        return true;
    }
    if (n <= 120 && item_markers >= 2 && page_noise >= 1) {
        return true;
    }
    if (n <= 120 && item_markers >= 3 && symbol_ratio >= 0.08) {
        return true;
    }
    if (n <= 80 && has_email && enum_refs >= 1) {
        return true;
    }
    return false;
}

static bool is_sentence_delimiter(uint32_t cp) {
    return cp == 0x3002 || cp == 0xFF01 || cp == 0xFF1F || cp == 0xFF1B ||
           cp == '!' || cp == '?' || cp == ';';
}

static std::string cp_slice(const std::string& s, const std::vector<CpPos>& cps, std::size_t l, std::size_t r) {
    if (l >= r || l >= cps.size()) {
        return "";
    }
    r = std::min(r, cps.size());
    std::size_t start = cps[l].byte_pos;
    std::size_t end = cps[r - 1].byte_pos + cps[r - 1].byte_len;
    return s.substr(start, end - start);
}

static std::string cp_tail(const std::string& s, std::size_t k) {
    auto cps = decode_all(s);
    if (k >= cps.size()) {
        return s;
    }
    return cp_slice(s, cps, cps.size() - k, cps.size());
}

static std::vector<std::string> split_sentences_cpp(const std::string& text) {
    auto cps = decode_all(text);
    std::vector<std::string> out;
    std::size_t start = 0;
    for (std::size_t i = 0; i < cps.size(); i++) {
        if (!is_sentence_delimiter(cps[i].cp)) {
            continue;
        }
        std::string part = trim_spaces(cp_slice(text, cps, start, i + 1));
        if (!part.empty()) {
            out.push_back(part);
        }
        start = i + 1;
    }
    if (start < cps.size()) {
        std::string part = trim_spaces(cp_slice(text, cps, start, cps.size()));
        if (!part.empty()) {
            out.push_back(part);
        }
    }
    return out;
}

static std::vector<std::string> chunk_text_cpp(const std::string& text, int chunk_size, int overlap) {
    if (chunk_size <= 0) {
        throw std::invalid_argument("chunk_size must be > 0");
    }
    if (overlap < 0) {
        throw std::invalid_argument("overlap must be >= 0");
    }
    if (overlap >= chunk_size) {
        throw std::invalid_argument("overlap must be smaller than chunk_size");
    }

    std::vector<std::string> sents = split_sentences_cpp(text);
    if (sents.empty()) {
        return {};
    }

    std::vector<std::string> chunks;
    std::string cur;

    for (const auto& sent : sents) {
        std::size_t sent_len = cp_len(sent);
        if ((int)sent_len > chunk_size) {
            if (!cur.empty()) {
                chunks.push_back(trim_spaces(cur));
                cur.clear();
            }
            auto cps = decode_all(sent);
            int step = chunk_size - overlap;
            std::size_t start = 0;
            while (start < cps.size()) {
                std::size_t end = std::min(cps.size(), start + (std::size_t)chunk_size);
                std::string piece = trim_spaces(cp_slice(sent, cps, start, end));
                if (!piece.empty()) {
                    chunks.push_back(piece);
                }
                if (end == cps.size()) {
                    break;
                }
                start += (std::size_t)step;
            }
            continue;
        }

        if (cur.empty()) {
            cur = sent;
            continue;
        }

        std::size_t cur_len = cp_len(cur);
        if ((int)(cur_len + sent_len) <= chunk_size) {
            cur += sent;
        } else {
            chunks.push_back(trim_spaces(cur));
            if (overlap > 0 && !chunks.empty()) {
                std::string tail = cp_tail(chunks.back(), (std::size_t)overlap);
                cur = trim_spaces(tail + sent);
            } else {
                cur = sent;
            }
        }
    }

    if (!cur.empty()) {
        chunks.push_back(trim_spaces(cur));
    }

    std::vector<std::string> out;
    out.reserve(chunks.size());
    for (const auto& c : chunks) {
        if (!c.empty()) {
            out.push_back(c);
        }
    }
    return out;
}

} // namespace

PYBIND11_MODULE(_text_ops, m) {
    m.doc() = "High-performance text operations for RAG preprocessing";

    m.def(
        "is_low_signal_text",
        [](const std::string& text) {
            return is_low_signal_text_cpp(text);
        },
        py::arg("text"),
        "Detect low-signal/noisy chunk text"
    );

    m.def(
        "chunk_text",
        [](const std::string& text, int chunk_size, int overlap) {
            return chunk_text_cpp(text, chunk_size, overlap);
        },
        py::arg("text"), py::arg("chunk_size"), py::arg("overlap"),
        "Split text into overlapping sentence-aware chunks"
    );
}
