#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, Generator, Iterable, List, Optional, Tuple


def iter_jsonl(path: str) -> Generator[Dict, None, None]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no} in {path}: {exc}") from exc


def first_non_empty(row: Dict, keys: Iterable[str]) -> str:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        if isinstance(v, str):
            t = v.strip()
            if t:
                return t
        else:
            return str(v)
    return "__NO_SECTION__"


def pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(100.0 * num / den, 4)


def build_markdown(report: Dict, top_n: int) -> str:
    lines: List[str] = []
    overall = report["overall"]

    lines.append("# Dedup Report")
    lines.append("")
    lines.append(f"Generated: {report['generated_at_utc']}")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- total_docs: {overall['total_docs']}")
    lines.append(f"- kept_docs: {overall['kept_docs']}")
    lines.append(f"- exact_dup: {overall['exact_dup']}")
    lines.append(f"- near_dup: {overall['near_dup']}")
    lines.append(f"- duplicated_docs: {overall['duplicated_docs']}")
    lines.append(f"- duplicated_rate_pct: {overall['duplicated_rate_pct']}")
    lines.append("")

    lines.append("## Near-Duplicate Distance Distribution")
    lines.append("")
    if report["near_distance_distribution"]:
        lines.append("| distance | count |")
        lines.append("|---:|---:|")
        for d, c in report["near_distance_distribution"].items():
            lines.append(f"| {d} | {c} |")
    else:
        lines.append("No near-duplicates found.")
    lines.append("")

    lines.append("## By Source (Top by duplicated docs)")
    lines.append("")
    lines.append("| source | total | exact | near | duplicated | dup_rate_pct |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in report["by_source"][:top_n]:
        lines.append(
            "| {source} | {total_docs} | {exact_dup} | {near_dup} | {duplicated_docs} | {duplicated_rate_pct} |".format(
                **row
            )
        )
    lines.append("")

    lines.append("## By Section (Top by duplicated docs)")
    lines.append("")
    lines.append("| section | total | exact | near | duplicated | dup_rate_pct |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in report["by_section"][:top_n]:
        lines.append(
            "| {section} | {total_docs} | {exact_dup} | {near_dup} | {duplicated_docs} | {duplicated_rate_pct} |".format(
                **row
            )
        )
    lines.append("")

    lines.append("## Threshold Hints")
    lines.append("")
    hints = report["threshold_hints"]
    lines.append(f"- near_dup_p50_distance: {hints['p50_distance']}")
    lines.append(f"- near_dup_p90_distance: {hints['p90_distance']}")
    lines.append(f"- near_dup_p95_distance: {hints['p95_distance']}")
    lines.append(
        "- suggestion: If many near-dup distances are well below your threshold, decrease `simhash-threshold`; "
        "if obvious duplicates are missed, increase it slightly."
    )
    lines.append("")
    return "\n".join(lines)


def percentile_from_counter(counter: Counter, q: float) -> Optional[int]:
    if not counter:
        return None
    total = sum(counter.values())
    if total <= 0:
        return None
    target = total * q
    acc = 0
    for d in sorted(counter):
        acc += counter[d]
        if acc >= target:
            return d
    return max(counter)


def make_stats_rows(
    totals: Dict[str, int],
    exact: Dict[str, int],
    near: Dict[str, int],
    key_name: str,
) -> List[Dict]:
    rows: List[Dict] = []
    for key, total in totals.items():
        e = exact.get(key, 0)
        n = near.get(key, 0)
        d = e + n
        rows.append(
            {
                key_name: key,
                "total_docs": total,
                "exact_dup": e,
                "near_dup": n,
                "duplicated_docs": d,
                "kept_docs": total - d,
                "duplicated_rate_pct": pct(d, total),
            }
        )
    rows.sort(key=lambda x: (x["duplicated_docs"], x["duplicated_rate_pct"]), reverse=True)
    return rows


def build_report(
    docs_path: str,
    dup_path: str,
    section_fields: List[str],
) -> Dict:
    total_docs = 0

    source_totals: Dict[str, int] = defaultdict(int)
    section_totals: Dict[str, int] = defaultdict(int)

    # doc_id -> (source, section)
    doc_map: Dict[str, Tuple[str, str]] = {}

    for row in iter_jsonl(docs_path):
        total_docs += 1
        doc_id = str(row.get("doc_id", f"__row_{total_docs}"))
        source = str(row.get("source", ""))
        section = first_non_empty(row, section_fields)

        source_totals[source] += 1
        section_totals[section] += 1
        doc_map[doc_id] = (source, section)

    exact_dup = 0
    near_dup = 0

    source_exact: Dict[str, int] = defaultdict(int)
    source_near: Dict[str, int] = defaultdict(int)
    section_exact: Dict[str, int] = defaultdict(int)
    section_near: Dict[str, int] = defaultdict(int)

    near_dist: Counter = Counter()

    for row in iter_jsonl(dup_path):
        dup_type = str(row.get("dup_type", "")).lower()
        doc_id = str(row.get("doc_id", ""))

        source, section = doc_map.get(doc_id, (str(row.get("source", "")), "__UNKNOWN__"))

        if dup_type == "exact":
            exact_dup += 1
            source_exact[source] += 1
            section_exact[section] += 1
        elif dup_type == "near":
            near_dup += 1
            source_near[source] += 1
            section_near[section] += 1
            dist = row.get("distance")
            if isinstance(dist, int):
                near_dist[dist] += 1
            elif isinstance(dist, str) and dist.isdigit():
                near_dist[int(dist)] += 1

    duplicated_docs = exact_dup + near_dup
    kept_docs = total_docs - duplicated_docs

    by_source = make_stats_rows(source_totals, source_exact, source_near, "source")
    by_section = make_stats_rows(section_totals, section_exact, section_near, "section")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "docs": os.path.abspath(docs_path),
            "duplicates": os.path.abspath(dup_path),
            "section_fields": section_fields,
        },
        "overall": {
            "total_docs": total_docs,
            "kept_docs": kept_docs,
            "exact_dup": exact_dup,
            "near_dup": near_dup,
            "duplicated_docs": duplicated_docs,
            "duplicated_rate_pct": pct(duplicated_docs, total_docs),
        },
        "near_distance_distribution": {str(k): near_dist[k] for k in sorted(near_dist)},
        "threshold_hints": {
            "p50_distance": percentile_from_counter(near_dist, 0.50),
            "p90_distance": percentile_from_counter(near_dist, 0.90),
            "p95_distance": percentile_from_counter(near_dist, 0.95),
        },
        "by_source": by_source,
        "by_section": by_section,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build dedup statistics report by source/section and near-dup distance distribution."
    )
    parser.add_argument("--docs", required=True, help="Input docs JSONL (before dedup)")
    parser.add_argument("--dups", required=True, help="Duplicate log JSONL from dedup step")
    parser.add_argument("--output-json", required=True, help="Output report JSON path")
    parser.add_argument(
        "--output-md",
        default=None,
        help="Optional output markdown summary path",
    )
    parser.add_argument(
        "--section-fields",
        default="section,chapter,章节,title,record_index",
        help=(
            "Comma-separated candidate fields for section grouping "
            "(first non-empty wins, default: section,chapter,章节,title,record_index)"
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Top N rows for markdown tables (default: 50)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    section_fields = [x.strip() for x in args.section_fields.split(",") if x.strip()]
    if not section_fields:
        section_fields = ["record_index"]

    report = build_report(args.docs, args.dups, section_fields)

    os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if args.output_md:
        os.makedirs(os.path.dirname(args.output_md) or ".", exist_ok=True)
        md = build_markdown(report, top_n=args.top_n)
        with open(args.output_md, "w", encoding="utf-8") as f:
            f.write(md)

    overall = report["overall"]
    print(
        (
            "done: "
            f"total_docs={overall['total_docs']} "
            f"kept_docs={overall['kept_docs']} "
            f"exact_dup={overall['exact_dup']} "
            f"near_dup={overall['near_dup']} "
            f"duplicated_rate_pct={overall['duplicated_rate_pct']}"
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
