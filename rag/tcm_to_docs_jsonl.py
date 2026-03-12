#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from hashlib import sha1
from typing import Dict, Generator, Iterable, Optional


# Common noisy patterns from OCR/book metadata pages.
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


def iter_json_array_objects(file_path: str) -> Generator[Dict, None, None]:
    """Stream objects from a top-level JSON array without full-file loading."""
    decoder = json.JSONDecoder()
    with open(file_path, "r", encoding="utf-8") as f:
        buf = ""
        in_array = False
        eof = False

        while True:
            chunk = f.read(1 << 20)
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


def extract_text_items(record: Dict) -> Iterable[str]:
    content = record.get("content")
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            yield text


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


def text_sha1(text: str) -> str:
    return sha1(text.encode("utf-8")).hexdigest()


def build_doc_id(source_path: str, record_index: int, text_index: int) -> str:
    raw = f"{os.path.abspath(source_path)}:{record_index}:{text_index}"
    return sha1(raw.encode("utf-8")).hexdigest()


def convert(
    input_path: str,
    output_path: str,
    min_len: int,
    limit_records: Optional[int],
    keep_url: bool,
) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    processed_records = 0
    written_docs = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for rec_idx, record in enumerate(iter_json_array_objects(input_path)):
            if limit_records is not None and processed_records >= limit_records:
                break

            record_type = record.get("type", "") if isinstance(record, dict) else ""
            for txt_idx, raw_text in enumerate(extract_text_items(record)):
                cleaned = clean_text(raw_text, keep_url=keep_url)
                if len(cleaned) < min_len:
                    continue

                doc_id = build_doc_id(input_path, rec_idx, txt_idx)
                row = {
                    "doc_id": doc_id,
                    "source": os.path.abspath(input_path),
                    "record_index": rec_idx,
                    "text_index": txt_idx,
                    "record_type": record_type,
                    "text": cleaned,
                    "char_len": len(cleaned),
                    "text_sha1": text_sha1(cleaned),
                    "stage": "cleaned_doc",
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                written_docs += 1

            processed_records += 1
            if processed_records % 10000 == 0:
                print(
                    f"processed_records={processed_records} written_docs={written_docs}",
                    file=sys.stderr,
                    flush=True,
                )

    print(
        f"done: input={input_path} output={output_path} records={processed_records} docs={written_docs}",
        file=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean TCM corpus JSON and write normalized document JSONL."
    )
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--output", required=True, help="Output docs JSONL file path")
    parser.add_argument(
        "--min-len",
        type=int,
        default=80,
        help="Drop cleaned docs shorter than this length (default: 80)",
    )
    parser.add_argument(
        "--limit-records",
        type=int,
        default=None,
        help="Process only first N records for quick test",
    )
    parser.add_argument(
        "--keep-url",
        action="store_true",
        help="Keep URLs in text (default removes URLs)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    convert(
        input_path=args.input,
        output_path=args.output,
        min_len=args.min_len,
        limit_records=args.limit_records,
        keep_url=args.keep_url,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
