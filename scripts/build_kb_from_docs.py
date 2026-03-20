#!/usr/bin/env python3
"""Batch-convert Word/PDF guideline files into knowledge_base.jsonl format.

Output record schema (one JSON per line):
- id: string
- title: string
- content: string
- tags: list[str]
- source: string

Examples:
  python scripts/build_kb_from_docs.py \
      --input-dir ./docs/guidelines \
      --output-file ./rag/kb/knowledge_base.jsonl \
      --id-prefix KB-HT

  python scripts/build_kb_from_docs.py \
      --input-dir ./docs \
      --output-file ./rag/kb/knowledge_base.jsonl \
      --append
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List, Sequence


def _read_docx(path: Path) -> str:
    try:
        from docx import Document  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "python-docx is required for .docx parsing. Install: pip install python-docx"
        ) from exc

    doc = Document(str(path))
    lines: List[str] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:
        raise RuntimeError("pypdf is required for .pdf parsing. Install: pip install pypdf") from exc

    reader = PdfReader(str(path))
    pages: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages.append(text)
    return "\n".join(pages)


def _normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\u3000", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_blocks(text: str) -> List[str]:
    if not text:
        return []
    blocks = [blk.strip() for blk in re.split(r"\n\s*\n", text) if blk.strip()]
    return blocks


def _chunk_block(block: str, max_chars: int) -> List[str]:
    if len(block) <= max_chars:
        return [block]

    sentences = re.split(r"(?<=[。！？!?；;])", block)
    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) <= max_chars:
            current += sentence
            continue
        if current:
            chunks.append(current)
        if len(sentence) <= max_chars:
            current = sentence
            continue
        # hard split oversized sentence
        start = 0
        while start < len(sentence):
            end = min(start + max_chars, len(sentence))
            chunks.append(sentence[start:end])
            start = end
        current = ""

    if current:
        chunks.append(current)

    return [item.strip() for item in chunks if item.strip()]


def _guess_tags(path: Path, text: str) -> List[str]:
    tags: List[str] = ["热成像"]
    lowered = f"{path.stem}\n{text}".lower()

    rules = {
        "诊断": ["诊断", "结论", "risk", "风险"],
        "治疗方案": ["治疗", "方案", "频次", "疗程", "干预"],
        "医生意见": ["医生意见", "建议", "评估"],
        "ROI": ["roi", "区域", "分区", "温差"],
        "禁忌": ["禁忌", "慎用", "不建议"],
        "复评": ["复评", "随访", "复测"],
    }

    for tag, keywords in rules.items():
        if any(keyword in lowered for keyword in keywords):
            tags.append(tag)

    unique = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique.append(tag)
    return unique


def _iter_docs(input_dir: Path, include_exts: Sequence[str]) -> Iterable[Path]:
    exts = {ext.lower() for ext in include_exts}
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in exts:
            yield path


def _build_entries_for_file(
    path: Path,
    source_root: Path,
    id_prefix: str,
    max_chars: int,
    min_chars: int,
) -> List[dict]:
    if path.suffix.lower() == ".docx":
        raw_text = _read_docx(path)
    elif path.suffix.lower() == ".pdf":
        raw_text = _read_pdf(path)
    else:
        return []

    normalized = _normalize_text(raw_text)
    if not normalized:
        return []

    blocks = _split_blocks(normalized)
    chunks: List[str] = []
    for block in blocks:
        chunks.extend(_chunk_block(block, max_chars=max_chars))

    chunks = [chunk for chunk in chunks if len(chunk) >= min_chars]
    if not chunks:
        return []

    rel_source = path.relative_to(source_root).as_posix()
    title_base = path.stem.strip() or "未命名文档"
    tags = _guess_tags(path, normalized[:1200])

    entries: List[dict] = []
    for idx, chunk in enumerate(chunks, start=1):
        item_id = f"{id_prefix}-{path.stem.upper().replace(' ', '-')}-{idx:03d}"
        item_id = re.sub(r"[^A-Z0-9_\-]", "", item_id)
        if not item_id:
            item_id = f"{id_prefix}-ITEM-{idx:03d}"

        title = title_base if idx == 1 else f"{title_base}（片段{idx}）"
        entries.append(
            {
                "id": item_id,
                "title": title,
                "content": chunk,
                "tags": tags,
                "source": rel_source,
            }
        )

    return entries


def build_jsonl(
    input_dir: Path,
    output_file: Path,
    id_prefix: str,
    max_chars: int,
    min_chars: int,
    append: bool,
    upsert: bool,
) -> int:
    docs = list(_iter_docs(input_dir, include_exts=(".docx", ".pdf")))
    if not docs:
        print(f"[WARN] No .docx/.pdf files found under: {input_dir}")
        return 0

    all_entries: List[dict] = []
    for path in docs:
        try:
            entries = _build_entries_for_file(
                path=path,
                source_root=input_dir,
                id_prefix=id_prefix,
                max_chars=max_chars,
                min_chars=min_chars,
            )
        except Exception as exc:
            print(f"[WARN] Skip file {path}: {exc}")
            continue

        if entries:
            all_entries.extend(entries)
            print(f"[OK] {path} -> {len(entries)} entries")
        else:
            print(f"[WARN] {path} -> no valid chunks")

    if not all_entries:
        print("[WARN] No entries generated.")
        return 0

    output_file.parent.mkdir(parents=True, exist_ok=True)

    if upsert and output_file.exists():
        existing_rows: List[dict] = []
        if output_file.suffix.lower() == ".json":
            try:
                data = json.loads(output_file.read_text(encoding="utf-8"))
                existing_rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
            except Exception as exc:
                print(f"[WARN] Failed to read existing JSON file: {exc}")
        else:
            with output_file.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        print(f"[WARN] Skip malformed existing row line={line_no}: {exc}")
                        continue
                    if isinstance(row, dict):
                        existing_rows.append(row)

        index_by_id = {
            str(row.get("id") or "").strip(): idx
            for idx, row in enumerate(existing_rows)
            if str(row.get("id") or "").strip()
        }

        replaced = 0
        added = 0
        for item in all_entries:
            item_id = str(item.get("id") or "").strip()
            if item_id and item_id in index_by_id:
                existing_rows[index_by_id[item_id]] = item
                replaced += 1
            else:
                existing_rows.append(item)
                if item_id:
                    index_by_id[item_id] = len(existing_rows) - 1
                added += 1

        if output_file.suffix.lower() == ".json":
            output_file.write_text(json.dumps(existing_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            with output_file.open("w", encoding="utf-8") as f:
                for row in existing_rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

        print(
            f"[DONE] Upserted {len(all_entries)} entries to: {output_file} "
            f"(added={added}, replaced={replaced}, total={len(existing_rows)})"
        )
        return len(all_entries)

    if output_file.suffix.lower() == ".json":
        existing: List[dict] = []
        if append and output_file.exists():
            try:
                data = json.loads(output_file.read_text(encoding="utf-8"))
                existing = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
            except Exception:
                pass
        output_file.write_text(json.dumps(existing + all_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        mode = "a" if append and output_file.exists() else "w"
        with output_file.open(mode, encoding="utf-8") as f:
            for item in all_entries:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[DONE] Wrote {len(all_entries)} entries to: {output_file}")
    return len(all_entries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build knowledge_base.jsonl from Word/PDF files")
    parser.add_argument("--input-dir", required=True, help="Directory containing .docx/.pdf guidelines")
    parser.add_argument(
        "--output-file",
        default="./rag/kb/knowledge_base.jsonl",
        help="Output file path (must be .jsonl; default: ./rag/kb/knowledge_base.jsonl)",
    )
    parser.add_argument("--id-prefix", default="KB-HT", help="ID prefix (default: KB-HT)")
    parser.add_argument("--max-chars", type=int, default=700, help="Max chars per chunk (default: 700)")
    parser.add_argument("--min-chars", type=int, default=80, help="Min chars per chunk (default: 80)")
    parser.add_argument("--append", action="store_true", help="Append to existing output file")
    parser.add_argument(
        "--upsert",
        action="store_true",
        help="Upsert by id into existing output file (replace same id, append new id)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_file = Path(args.output_file).resolve()

    if output_file.suffix.lower() != ".jsonl":
        print(
            "[ERROR] --output-file must be .jsonl. "
            "Use scripts/kb_jsonl_to_json.py to generate knowledge_base.json."
        )
        return 2

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[ERROR] input directory not found: {input_dir}")
        return 2

    written = build_jsonl(
        input_dir=input_dir,
        output_file=output_file,
        id_prefix=str(args.id_prefix).strip() or "KB-HT",
        max_chars=max(200, int(args.max_chars)),
        min_chars=max(20, int(args.min_chars)),
        append=bool(args.append),
        upsert=bool(args.upsert),
    )
    return 0 if written >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
