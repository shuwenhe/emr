from __future__ import annotations

import hashlib
import os
import re
from typing import Iterable, List


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
