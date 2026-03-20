#!/usr/bin/env python3
"""Batch-extract rule-like entries from Markdown files into knowledge_base.jsonl.

Examples:
  python scripts/build_kb_from_md.py \
      --input-dir ./docs \
      --output-file ./rag/kb/knowledge_base.jsonl \
      --id-prefix KB-MD \
      --upsert

  python scripts/build_kb_from_md.py \
      --input-dir ./docs \
      --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set


def _iter_markdown(input_dir: Path, include_exts: Sequence[str]) -> Iterable[Path]:
    exts = {ext.lower() for ext in include_exts}
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in exts:
            yield path


def _filter_markdown_paths(
    docs: List[Path],
    input_dir: Path,
    include_regex: str,
    exclude_regex: str,
) -> List[Path]:
    include_re = re.compile(include_regex, re.IGNORECASE) if include_regex else None
    exclude_re = re.compile(exclude_regex, re.IGNORECASE) if exclude_regex else None

    filtered: List[Path] = []
    for path in docs:
        rel = path.relative_to(input_dir).as_posix()
        if include_re and not include_re.search(rel):
            continue
        if exclude_re and exclude_re.search(rel):
            continue
        filtered.append(path)
    return filtered


def _normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"```[\s\S]*?```", "\n", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1", text)
    text = re.sub(r"^\s{0,3}[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_blocks(markdown_text: str) -> List[str]:
    if not markdown_text:
        return []

    lines = markdown_text.splitlines()
    blocks: List[str] = []
    current: List[str] = []
    heading = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                current.append("")
            continue

        if stripped.startswith("#"):
            if current:
                block = "\n".join(current).strip()
                if block:
                    blocks.append(block)
                current = []
            heading = re.sub(r"^#+\s*", "", stripped).strip()
            continue

        if heading and not current:
            current.append(heading)
        current.append(stripped)

    if current:
        block = "\n".join(current).strip()
        if block:
            blocks.append(block)

    cleaned = [_normalize_text(block) for block in blocks]
    return [item for item in cleaned if item]


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

        start = 0
        while start < len(sentence):
            end = min(start + max_chars, len(sentence))
            chunks.append(sentence[start:end])
            start = end
        current = ""

    if current:
        chunks.append(current)

    return [item.strip() for item in chunks if item.strip()]


def _guess_tags_and_sections(text: str, title: str) -> Dict[str, List[str]]:
    joined = f"{title}\n{text}".lower()

    tag_rules = {
        "检查准备": ["检查前", "静息", "准备", "环境"],
        "判读原则": ["判读", "对称", "温差", "绝对温度"],
        "风险分层": ["低风险", "中风险", "高风险", "风险分层"],
        "医生意见": ["医生意见", "建议", "复评", "仅供参考"],
        "治疗建议": ["治疗", "疗程", "频次", "理疗", "干预"],
        "禁忌": ["禁忌", "转诊", "红旗", "慎用"],
    }

    section_rules = {
        "report_note": ["检查前", "准备", "说明", "仅供参考"],
        "diagnosis": ["判读", "结论", "风险分层", "温差", "异常"],
        "doctor_opinion": ["建议", "复评", "随访", "医生意见", "转诊"],
        "treatment_plan_text": ["治疗", "疗程", "频次", "理疗", "干预"],
    }

    tags: List[str] = ["热成像"]
    for tag, keys in tag_rules.items():
        if any(key in joined for key in keys):
            tags.append(tag)

    sections: List[str] = []
    for section, keys in section_rules.items():
        if any(key in joined for key in keys):
            sections.append(section)

    if not sections:
        sections = ["report_note"]

    dedup_tags: List[str] = []
    seen: Set[str] = set()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            dedup_tags.append(tag)

    return {"tags": dedup_tags, "report_sections": sections}


def _guess_body_parts(text: str) -> List[str]:
    joined = text.lower()
    body_rules = {
        "颈肩": ["颈", "肩", "肩背", "颈肩"],
        "腰背": ["腰", "背", "腰背"],
        "膝关节": ["膝", "膝关节"],
        "四肢": ["四肢", "手", "足", "腕", "肘", "踝"],
    }
    out: List[str] = []
    for name, keys in body_rules.items():
        if any(key in joined for key in keys):
            out.append(name)
    return out


def _guess_risk_levels(text: str) -> List[str]:
    joined = text.lower()
    levels: List[str] = []
    if "低风险" in joined:
        levels.append("low")
    if "中风险" in joined:
        levels.append("medium")
    if "高风险" in joined:
        levels.append("high")
    return levels


def _priority(text: str) -> int:
    joined = text.lower()
    if any(key in joined for key in ["禁忌", "转诊", "红旗", "严重"]):
        return 10
    if any(key in joined for key in ["风险", "判读", "复评"]):
        return 9
    return 8


def _make_id(prefix: str, source: str, idx: int, content: str) -> str:
    stem = Path(source).stem.upper()
    stem = re.sub(r"[^A-Z0-9_\-]", "", stem)
    digest = hashlib.sha1(content[:200].encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{stem}-{idx:03d}-{digest}"


def _build_entries_for_file(
    path: Path,
    source_root: Path,
    id_prefix: str,
    max_chars: int,
    min_chars: int,
) -> List[dict]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    blocks = _split_blocks(raw)

    chunks: List[str] = []
    for block in blocks:
        chunks.extend(_chunk_block(block, max_chars=max_chars))

    chunks = [chunk for chunk in chunks if len(chunk) >= min_chars]
    if not chunks:
        return []

    rel_source = path.relative_to(source_root).as_posix()
    title_base = path.stem.strip() or "未命名文档"

    entries: List[dict] = []
    for idx, chunk in enumerate(chunks, start=1):
        title = title_base if idx == 1 else f"{title_base}（片段{idx}）"
        meta = _guess_tags_and_sections(chunk, title)
        risk_levels = _guess_risk_levels(chunk)
        body_parts = _guess_body_parts(chunk)

        retrieval_hints = [title]
        retrieval_hints.extend(meta["tags"][:4])
        if risk_levels:
            retrieval_hints.extend(risk_levels)
        if body_parts:
            retrieval_hints.extend(body_parts)

        entry = {
            "id": _make_id(id_prefix, rel_source, idx, chunk),
            "title": title,
            "content": chunk,
            "category": "guideline_markdown",
            "report_sections": meta["report_sections"],
            "tags": meta["tags"],
            "source": rel_source,
            "source_type": "guideline_doc",
            "priority": _priority(chunk),
            "status": "active",
            "applicable_conditions": [],
            "contraindications": [],
            "patient_scope": ["adult"],
            "body_parts": body_parts,
            "risk_levels": risk_levels,
            "evidence_level": "guideline_doc",
            "retrieval_hints": retrieval_hints,
        }
        entries.append(entry)

    return entries


def _upsert_jsonl(output_file: Path, all_entries: List[dict]) -> None:
    existing_rows: List[dict] = []
    if output_file.exists():
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

    added = 0
    replaced = 0
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

    output_file.parent.mkdir(parents=True, exist_ok=True)
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


def build_jsonl(
    input_dir: Path,
    output_file: Path,
    id_prefix: str,
    max_chars: int,
    min_chars: int,
    upsert: bool,
    dry_run: bool,
    include_regex: str,
    exclude_regex: str,
) -> int:
    docs = list(_iter_markdown(input_dir, include_exts=(".md", ".markdown")))
    docs = _filter_markdown_paths(
        docs,
        input_dir=input_dir,
        include_regex=include_regex,
        exclude_regex=exclude_regex,
    )
    if not docs:
        print(f"[WARN] No markdown files found under: {input_dir} (after filters)")
        return 0

    all_entries: List[dict] = []
    for path in docs:
        entries = _build_entries_for_file(
            path=path,
            source_root=input_dir,
            id_prefix=id_prefix,
            max_chars=max_chars,
            min_chars=min_chars,
        )
        if entries:
            all_entries.extend(entries)
            print(f"[OK] {path} -> {len(entries)} entries")

    if not all_entries:
        print("[WARN] No entries generated.")
        return 0

    if dry_run:
        print(f"[DRY-RUN] Generated entries: {len(all_entries)}")
        print(json.dumps(all_entries[0], ensure_ascii=False, indent=2))
        return len(all_entries)

    if upsert:
        _upsert_jsonl(output_file, all_entries)
    else:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        if output_file.suffix.lower() == ".json":
            existing_append: List[dict] = []
            if output_file.exists():
                try:
                    data = json.loads(output_file.read_text(encoding="utf-8"))
                    existing_append = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
                except Exception:
                    pass
            output_file.write_text(json.dumps(existing_append + all_entries, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            with output_file.open("a", encoding="utf-8") as f:
                for item in all_entries:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"[DONE] Appended {len(all_entries)} entries to: {output_file}")

    return len(all_entries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build knowledge_base.jsonl from markdown files")
    parser.add_argument("--input-dir", required=True, help="Directory containing markdown files")
    parser.add_argument(
        "--output-file",
        default="./rag/kb/knowledge_base.jsonl",
        help="Output file path (must be .jsonl; default: ./rag/kb/knowledge_base.jsonl)",
    )
    parser.add_argument("--id-prefix", default="KB-MD", help="ID prefix (default: KB-MD)")
    parser.add_argument("--max-chars", type=int, default=700, help="Max chars per chunk (default: 700)")
    parser.add_argument("--min-chars", type=int, default=80, help="Min chars per chunk (default: 80)")
    parser.add_argument("--upsert", action="store_true", help="Upsert by id into existing output file")
    parser.add_argument("--dry-run", action="store_true", help="Generate without writing output file")
    parser.add_argument(
        "--include-regex",
        default="",
        help="Only include markdown files whose relative path matches this regex",
    )
    parser.add_argument(
        "--exclude-regex",
        default="",
        help="Exclude markdown files whose relative path matches this regex",
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

    build_jsonl(
        input_dir=input_dir,
        output_file=output_file,
        id_prefix=str(args.id_prefix).strip() or "KB-MD",
        max_chars=max(200, int(args.max_chars)),
        min_chars=max(20, int(args.min_chars)),
        upsert=bool(args.upsert),
        dry_run=bool(args.dry_run),
        include_regex=str(args.include_regex or "").strip(),
        exclude_regex=str(args.exclude_regex or "").strip(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
