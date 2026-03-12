from __future__ import annotations

import glob
import hashlib
import importlib.util
import os
import re
from typing import Iterable, List


_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DOT_LEADER_RE = re.compile(r"[\.·•‧⋯…]{3,}")
_PAGE_REF_RE = re.compile(r"[\(（]\s*\d{1,4}\s*[\)）]")
_ENUM_MARKER_RE = re.compile(r"(?:^|\s)[0-9一二三四五六七八九十]+[、\.．:：)]")
_USEFUL_CHAR_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")
_TOC_HINT_RE = re.compile(r"(?:目\s*录|目录|第[一二三四五六七八九十百0-9]+章)")
_PAGE_NOISE_RE = re.compile(r"(?:^|[\s/·\.\-_])\d{1,4}(?=$|[\s/·\.\-_])")
_SYMBOL_RE = re.compile(r"[·\./\\\-_+*=~:：\(\)（）]")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")
_ITEM_MARKER_RE = re.compile(r"(?:^|\s)[0-9一二三四五六七八九十]{1,3}[、\.．)]")


try:
    _rag_dir = os.path.dirname(__file__)
    _so_paths = glob.glob(os.path.join(_rag_dir, "_text_ops*.so"))
    if _so_paths:
        _spec = importlib.util.spec_from_file_location("_text_ops", _so_paths[0])
        _text_ops_ext = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_text_ops_ext)  # type: ignore[union-attr]
        _USE_CPP_TEXT_OPS = True
    else:
        _text_ops_ext = None
        _USE_CPP_TEXT_OPS = False
except Exception:
    _text_ops_ext = None
    _USE_CPP_TEXT_OPS = False


def sha1_file(path: str) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def safe_relpath(path: str, base: str) -> str:
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def sanitize_embedding_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\u00a0", " ")
    text = _CONTROL_CHAR_RE.sub(" ", text)
    text = _DOT_LEADER_RE.sub(" ", text)
    return normalize_text(text)


def sanitize_embedding_text_aggressive(text: str) -> str:
    """Stronger sanitizer used only when embedding retries keep failing."""
    text = sanitize_embedding_text(text)
    text = _PAGE_REF_RE.sub(" ", text)
    text = _PAGE_NOISE_RE.sub(" ", text)
    text = re.sub(r"[+*=~]{2,}", " ", text)
    text = re.sub(r"[/\\|]{2,}", " ", text)
    text = re.sub(r"\.{2,}", " ", text)
    return normalize_text(text)


def _is_low_signal_text_py(text: str) -> bool:
    normalized = normalize_text(_CONTROL_CHAR_RE.sub(" ", text))
    if not normalized:
        return True
    useful_ratio = len(_USEFUL_CHAR_RE.findall(normalized)) / max(len(normalized), 1)
    has_dot_leader = bool(_DOT_LEADER_RE.search(text))
    page_refs = len(_PAGE_REF_RE.findall(text))
    enum_refs = len(_ENUM_MARKER_RE.findall(text))
    page_noise = len(_PAGE_NOISE_RE.findall(normalized))
    symbol_ratio = len(_SYMBOL_RE.findall(normalized)) / max(len(normalized), 1)
    toc_hint = bool(_TOC_HINT_RE.search(normalized))
    has_email = bool(_EMAIL_RE.search(normalized))
    item_markers = len(_ITEM_MARKER_RE.findall(normalized))
    if len(normalized) <= 120 and has_dot_leader and useful_ratio < 0.62:
        return True
    if len(normalized) <= 160 and has_dot_leader and page_refs >= 1 and enum_refs >= 1 and useful_ratio < 0.68:
        return True
    if len(normalized) <= 90 and toc_hint and page_noise >= 1:
        return True
    if len(normalized) <= 110 and page_noise >= 2 and enum_refs >= 1 and symbol_ratio >= 0.12:
        return True
    if len(normalized) <= 120 and item_markers >= 2 and page_noise >= 1:
        return True
    if len(normalized) <= 120 and item_markers >= 3 and symbol_ratio >= 0.08:
        return True
    if len(normalized) <= 80 and has_email and enum_refs >= 1:
        return True
    return False


def is_low_signal_text(text: str) -> bool:
    if _USE_CPP_TEXT_OPS:
        try:
            return bool(_text_ops_ext.is_low_signal_text(text))  # type: ignore[union-attr]
        except Exception:
            return _is_low_signal_text_py(text)
    return _is_low_signal_text_py(text)


def _split_sentences_py(text: str) -> List[str]:
    parts = re.split(r"(?<=[。！？；!?;])", text)
    out: List[str] = []
    for part in parts:
        p = part.strip()
        if p:
            out.append(p)
    return out


def _chunk_text_py(text: str, chunk_size: int, overlap: int) -> List[str]:
    sents = _split_sentences_py(text)
    if not sents:
        return []

    chunks: List[str] = []
    cur = ""
    for sent in sents:
        if len(sent) > chunk_size:
            if cur:
                chunks.append(cur.strip())
                cur = ""
            start = 0
            step = chunk_size - overlap
            while start < len(sent):
                end = min(len(sent), start + chunk_size)
                piece = sent[start:end].strip()
                if piece:
                    chunks.append(piece)
                if end == len(sent):
                    break
                start += step
            continue

        if not cur:
            cur = sent
            continue

        if len(cur) + len(sent) <= chunk_size:
            cur += sent
        else:
            chunks.append(cur.strip())
            if overlap > 0 and chunks:
                tail = chunks[-1][-overlap:]
                cur = (tail + sent).strip()
            else:
                cur = sent

    if cur:
        chunks.append(cur.strip())

    return [c for c in chunks if c]


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if _USE_CPP_TEXT_OPS:
        try:
            return list(_text_ops_ext.chunk_text(text, chunk_size, overlap))  # type: ignore[union-attr]
        except Exception:
            return _chunk_text_py(text, chunk_size, overlap)
    return _chunk_text_py(text, chunk_size, overlap)


def split_text(text: str, max_len: int, overlap: int) -> List[str]:
    if max_len <= 0:
        return [text]
    if len(text) <= max_len:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_len)
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def table_to_markdown(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    header = [escape_md(cell) for cell in header]
    data_rows = [[escape_md(cell) for cell in row] for row in rows[1:]]
    cols = len(header)
    if cols == 0:
        return ""
    sep = ["---"] * cols
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    for row in data_rows:
        padded = row + [""] * (cols - len(row))
        lines.append("| " + " | ".join(padded[:cols]) + " |")
    return "\n".join(lines)


def table_to_linearized_text(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    lines: List[str] = []
    if body:
        for row in body:
            pairs = []
            for idx, cell in enumerate(row):
                key = header[idx] if idx < len(header) else f"col{idx + 1}"
                pairs.append(f"{key}: {cell}")
            lines.append("; ".join(pairs))
    else:
        pairs = []
        for idx, cell in enumerate(header):
            pairs.append(f"col{idx + 1}: {cell}")
        lines.append("; ".join(pairs))
    return "\n".join(lines)


def iter_batches(items: List[str], batch_size: int) -> Iterable[List[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


_LIST_ITEM_RE = re.compile(
    r"(?:^|\s)(?:"
    r"\d{1,2}[\u3001\.\)]"
    r"|\(\d{1,2}\)"
    r"|\uff08\d{1,2}\uff09"
    r"|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u3001]"
    r"|[\u2460-\u2469]"
    r")"
)


def split_list_items(text: str) -> List[str]:
    matches = list(_LIST_ITEM_RE.finditer(text))
    if len(matches) <= 1:
        return [text]
    items: List[str] = []
    if matches[0].start() > 0:
        prefix = text[: matches[0].start()].strip()
        if prefix:
            items.append(prefix)
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        item = text[start:end].strip()
        if item:
            items.append(item)
    return items
