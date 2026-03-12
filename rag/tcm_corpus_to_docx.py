#!/usr/bin/env python3
"""
tcm_corpus_to_docx.py
======================
Convert TCM_pretrain_book_corpus.json into a directory of .docx files
that are directly consumable by the existing ``make kb-build`` pipeline
(``kb_builder.py`` / ``parse_docx()``).

Each .docx file contains ``--records-per-docx`` records.
Inside the file every record becomes:

    Heading 1:  <first ~60 chars of text>  [used as title_path context]
    Normal:     <full cleaned paragraph text>

This structure lets ``_collect_chunks()`` in kb_builder.py attach the
record's opening line as title context to every embedding.

Usage
-----
    # Convert the whole corpus (≈1 M records → ~2 000 docx files at 500/file)
    python rag/tcm_corpus_to_docx.py \\
        --input  rag/dataset/TCM_pretrain_book_corpus.json \\
        --output-dir rag/dataset/docx_corpus \\
        --records-per-docx 500

    # Smoke-test: first 200 records only
    python rag/tcm_corpus_to_docx.py \\
        --input  rag/dataset/TCM_pretrain_book_corpus.json \\
        --output-dir /tmp/tcm_docx_test \\
        --limit-records 200

Then build the knowledge base:
    make kb-build KB_SOURCE_DIR=rag/dataset/docx_corpus
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, Generator, Iterable, List, Optional

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT


# ---------------------------------------------------------------------------
# Noise / cleaning (same rules as tcm_to_docs_jsonl.py)
# ---------------------------------------------------------------------------

NOISE_PATTERNS = [
    r"中国版本图书馆CIP数据核字",
    r"图书在版编目\s*\(CIP\)",
    r"版权专有侵权必究",
    r"各地新华书店经销",
    r"服务热线\d{6,}",
    r"传真\d{6,}",
    r"天猫旗舰店网址",
    r"微商城网址",
    r"ISBN\s*\d[\d\-Xx]+",
]
NOISE_REGEXES = [re.compile(p) for p in NOISE_PATTERNS]

LATEX_CLEANUPS = [
    (re.compile(r"\$\\textcircled\{\d+\}\$"), " "),
    (re.compile(r"\$[^$]{1,80}\$"), " "),
    (re.compile(r"\\[a-zA-Z]+\{[^{}]{0,80}\}"), " "),
]

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
WS_RE = re.compile(r"[ \t\u3000]+")
MULTI_NL_RE = re.compile(r"\n{3,}")

# Strip characters that are illegal in XML 1.0 (null bytes, most C0/C1 controls)
# Allowed: tab (0x09), LF (0x0A), CR (0x0D), 0x20-0xD7FF, 0xE000-0xFFFD
_XML_ILLEGAL = re.compile(
    r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]"
)


def sanitize_xml(text: str) -> str:
    """Remove characters that are not valid in XML 1.0 documents."""
    return _XML_ILLEGAL.sub("", text)


def clean_text(text: str, keep_url: bool = False) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for regex, repl in LATEX_CLEANUPS:
        text = regex.sub(repl, text)
    if not keep_url:
        text = URL_RE.sub(" ", text)
    for regex in NOISE_REGEXES:
        text = regex.sub(" ", text)
    text = re.sub(r"\s+([，。；：！？）】》」』])", r"\1", text)
    text = re.sub(r"([（【《「『])\s+", r"\1", text)
    text = WS_RE.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Streaming JSON array reader
# ---------------------------------------------------------------------------

def iter_json_array_objects(file_path: str) -> Generator[Dict, None, None]:
    """Yield objects from a top-level JSON array without loading the whole file."""
    decoder = json.JSONDecoder()
    with open(file_path, "r", encoding="utf-8") as fh:
        buf = ""
        in_array = False
        eof = False
        while True:
            chunk = fh.read(1 << 20)
            if chunk:
                buf += chunk
            else:
                eof = True
            if not in_array:
                stripped = buf.lstrip()
                if not stripped:
                    if eof:
                        return
                    continue
                if stripped[0] != "[":
                    raise ValueError("Input JSON must be a top-level array")
                buf = stripped[1:]
                in_array = True
            while True:
                stripped = buf.lstrip()
                if not stripped:
                    break
                if stripped[0] == "]":
                    return
                if stripped[0] == ",":
                    buf = stripped[1:]
                    continue
                try:
                    obj, idx = decoder.raw_decode(stripped)
                except json.JSONDecodeError:
                    if eof:
                        raise
                    break
                yield obj
                buf = stripped[idx:]
            if eof:
                break


def extract_texts(record: Dict) -> Iterable[str]:
    content = record.get("content")
    if not isinstance(content, list):
        return
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                yield text


# ---------------------------------------------------------------------------
# Docx writer
# ---------------------------------------------------------------------------

def _make_title(text: str, max_len: int = 60) -> str:
    """Use first line (up to max_len chars) as a section heading."""
    first_line = text.split("\n")[0].strip()
    if len(first_line) <= max_len:
        return first_line or text[:max_len]
    return first_line[:max_len].rstrip()


def write_docx(records: List[Dict], output_path: str, keep_url: bool = False, min_len: int = 0) -> int:
    """
    Write one docx file from a list of corpus records.
    Returns the number of records actually written (skipped empty/too-short).
    """
    doc = Document()

    # Remove the default empty paragraph Word adds at the top
    for p in doc.paragraphs:
        p._element.getparent().remove(p._element)

    written = 0
    for record in records:
        texts = [clean_text(t, keep_url) for t in extract_texts(record)]
        texts = [t for t in texts if len(t) >= max(min_len, 1)]
        if not texts:
            continue

        full_text = "\n\n".join(texts)
        full_text = sanitize_xml(full_text)

        # Heading 1 — first ~60 chars of text (used as title_path by kb_builder)
        heading = doc.add_heading(_make_title(full_text), level=1)
        heading.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
        for run in heading.runs:
            run.font.size = Pt(12)

        # Body — one Normal paragraph per text block (split on blank lines)
        for segment in re.split(r"\n{2,}", full_text):
            segment = segment.strip()
            if segment:
                doc.add_paragraph(segment)

        written += 1

    doc.save(output_path)
    return written


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def convert(
    input_path: str,
    output_dir: str,
    records_per_docx: int = 500,
    min_len: int = 80,
    limit_records: Optional[int] = None,
    keep_url: bool = False,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    batch: List[Dict] = []
    file_index = 0
    total_records = 0
    total_written = 0  # paragraphs that passed min_len

    def flush(batch: List[Dict], index: int) -> int:
        out_path = os.path.join(output_dir, f"tcm_part_{index:06d}.docx")
        n = write_docx(batch, out_path, keep_url=keep_url, min_len=min_len)
        return n

    print(f"Reading: {input_path}")
    print(f"Output:  {output_dir}")
    print(f"Records per docx: {records_per_docx}  min_len: {min_len}")
    if limit_records:
        print(f"Limit: {limit_records} records")

    for record in iter_json_array_objects(input_path):
        batch.append(record)
        total_records += 1

        if total_records % 10_000 == 0:
            print(f"  read {total_records:,}  files written {file_index:,}", flush=True)

        if len(batch) >= records_per_docx:
            total_written += flush(batch, file_index)
            file_index += 1
            batch = []

        if limit_records is not None and total_records >= limit_records:
            break

    # flush remainder
    if batch:
        total_written += flush(batch, file_index)
        file_index += 1

    print(
        f"\nDone. records_read={total_records:,}  "
        f"records_written={total_written:,}  "
        f"docx_files={file_index:,}  "
        f"output_dir={output_dir}"
    )
    print(f"\nTo build the KB:")
    print(f"  make kb-build KB_SOURCE_DIR={output_dir}")
    print(f"  # or directly:")
    print(
        f"  PYTHONPATH=/home/shuwen/emr /home/shuwen/.venv/bin/python -c \""
        f"from rag.kb_builder import build_kb; "
        f"build_kb(source_dir='{output_dir}', out_dir='rag/kb', "
        f"provider='ollama', embed_model='bge-m3:latest', "
        f"base_url=None, api_key=None)\""
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert TCM_pretrain_book_corpus.json → directory of .docx files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--input",
        default="rag/dataset/TCM_pretrain_book_corpus.json",
        help="Path to TCM_pretrain_book_corpus.json.",
    )
    p.add_argument(
        "--output-dir",
        default="rag/dataset/docx_corpus",
        help="Directory to write .docx files into.",
    )
    p.add_argument(
        "--records-per-docx",
        type=int,
        default=500,
        metavar="N",
        help="Number of corpus records to pack into each .docx file.",
    )
    p.add_argument(
        "--min-len",
        type=int,
        default=80,
        metavar="N",
        help="Skip text blocks shorter than N characters after cleaning.",
    )
    p.add_argument(
        "--limit-records",
        type=int,
        default=None,
        metavar="N",
        help="Stop after processing N records (for testing).",
    )
    p.add_argument(
        "--keep-url",
        action="store_true",
        help="Keep HTTP/HTTPS URLs instead of removing them.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    convert(
        input_path=args.input,
        output_dir=args.output_dir,
        records_per_docx=args.records_per_docx,
        min_len=args.min_len,
        limit_records=args.limit_records,
        keep_url=args.keep_url,
    )


if __name__ == "__main__":
    main()
