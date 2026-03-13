#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import glob
import importlib.util
from concurrent.futures import Future, ProcessPoolExecutor
from collections import Counter, defaultdict
from collections import deque
from hashlib import sha1
from typing import Deque, DefaultDict, Dict, Generator, List, Optional, Tuple


try:
    _rag_dir = os.path.dirname(__file__)
    _so_paths = []
    _so_paths.extend(glob.glob(os.path.join(_rag_dir, "so", "_simhash*.so")))
    _so_paths.extend(glob.glob(os.path.join(_rag_dir, "_simhash*.so")))
    _so_paths.extend(glob.glob(os.path.join(_rag_dir, "simhash", "_simhash*.so")))
    if _so_paths:
        _spec = importlib.util.spec_from_file_location("_simhash", _so_paths[0])
        _simhash_ext = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_simhash_ext)  # type: ignore[union-attr]
        _USE_CPP = True
        _USE_CPP_SWEEP = hasattr(_simhash_ext, "ThresholdSweepEngine")
    else:
        _simhash_ext = None
        _USE_CPP = False
        _USE_CPP_SWEEP = False
except Exception:
    _simhash_ext = None
    _USE_CPP = False
    _USE_CPP_SWEEP = False


TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


def iter_jsonl(path: str) -> Generator[Dict, None, None]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc


def tokenize(text: str) -> List[str]:
    if _USE_CPP:
        return _simhash_ext.tokenize(text)  # type: ignore[union-attr]
    return TOKEN_RE.findall(text.lower())


def simhash64(text: str) -> int:
    if _USE_CPP:
        return _simhash_ext.simhash64(text)  # type: ignore[union-attr]
    tokens = tokenize(text)
    if not tokens:
        return 0

    counts = Counter(tokens)
    vec = [0] * 64
    for tok, w in counts.items():
        h = int.from_bytes(sha1(tok.encode("utf-8")).digest()[:8], "big", signed=False)
        for i in range(64):
            if (h >> i) & 1:
                vec[i] += w
            else:
                vec[i] -= w

    out = 0
    for i, v in enumerate(vec):
        if v >= 0:
            out |= 1 << i
    return out


def simhash64_worker(text: str) -> int:
    if _USE_CPP:
        return _simhash_ext.simhash64_worker(text)  # type: ignore[union-attr]
    return simhash64(text)


def hamming_distance(a: int, b: int) -> int:
    if _USE_CPP:
        return _simhash_ext.hamming_distance(a, b)  # type: ignore[union-attr]
    return (a ^ b).bit_count()


def band_keys(fp: int, bands: int) -> List[Tuple[int, int]]:
    if bands <= 0 or 64 % bands != 0:
        raise ValueError("bands must be a positive divisor of 64")
    width = 64 // bands
    mask = (1 << width) - 1
    out = []
    for b in range(bands):
        out.append((b, (fp >> (b * width)) & mask))
    return out


def percentile(counter: Counter, q: float) -> Optional[int]:
    if not counter:
        return None
    total = sum(counter.values())
    if total <= 0:
        return None
    target = total * q
    acc = 0
    for k in sorted(counter):
        acc += counter[k]
        if acc >= target:
            return k
    return max(counter)


def pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(num * 100.0 / den, 4)


class State:
    def __init__(self, bands: int) -> None:
        self.bands = bands
        self.seen_sha1: set[str] = set()
        self.kept_doc_ids: List[str] = []
        self.kept_fp: List[int] = []
        self.kept_sha1: List[str] = []
        self.buckets: DefaultDict[Tuple[int, int], List[int]] = defaultdict(list)

        self.total = 0
        self.kept = 0
        self.exact_dup = 0
        self.near_dup = 0
        self.too_short = 0
        self.near_dist: Counter = Counter()


def choose_recommended(rows: List[Dict]) -> Optional[int]:
    if not rows:
        return None
    max_near = max(r["near_dup"] for r in rows)
    target = max_near * 0.95
    candidates = [r for r in rows if r["near_dup"] >= target]
    if not candidates:
        candidates = rows
    # Prefer conservative threshold among near-optimal dedup gains.
    return min(r["threshold"] for r in candidates)


def build_markdown(summary: Dict) -> str:
    lines: List[str] = []
    lines.append("# SimHash Threshold Sweep")
    lines.append("")
    lines.append(f"Input: {summary['input']}")
    lines.append(f"Bands: {summary['bands']}")
    lines.append(f"Min length: {summary['min_len']}")
    lines.append("")
    lines.append(f"Recommended threshold: {summary['recommended_threshold']}")
    lines.append("")
    lines.append("| threshold | total | kept | exact_dup | near_dup | duplicated_rate_pct | near_p50 | near_p90 | near_p95 |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in summary["results"]:
        lines.append(
            "| {threshold} | {total} | {kept} | {exact_dup} | {near_dup} | {duplicated_rate_pct} | {near_p50} | {near_p90} | {near_p95} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("Selection rule: choose the smallest threshold whose near-duplicate count reaches at least 95% of the maximum near-duplicate count.")
    return "\n".join(lines)


def parse_thresholds(raw: str) -> List[int]:
    vals: List[int] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        vals.append(int(p))
    vals = sorted(set(vals))
    if not vals:
        raise ValueError("No valid thresholds provided")
    if any(v < 0 for v in vals):
        raise ValueError("Thresholds must be >= 0")
    return vals


def sweep(
    input_path: str,
    thresholds: List[int],
    bands: int,
    min_len: int,
    limit_docs: Optional[int],
    progress_every: int,
    parallel_workers: int,
) -> Dict:
    total = 0
    too_short = 0

    if _USE_CPP_SWEEP:
        engine = _simhash_ext.ThresholdSweepEngine(thresholds, bands)  # type: ignore[union-attr]
        if limit_docs is not None and limit_docs > 0:
            engine.reserve(limit_docs)

        max_pending = max(1, parallel_workers * 8)
        pending: Deque[Tuple[str, Future[int]]] = deque()

        def process_ready(text_sha1: str, fp: int) -> None:
            engine.process(fp, text_sha1)

        if parallel_workers <= 1:
            for idx, row in enumerate(iter_jsonl(input_path), start=1):
                if limit_docs is not None and idx > limit_docs:
                    break

                total += 1

                text = row.get("text")
                if not isinstance(text, str):
                    continue
                text = text.strip()

                if len(text) < min_len:
                    too_short += 1
                    continue

                text_sha1 = row.get("text_sha1")
                if not isinstance(text_sha1, str) or not text_sha1:
                    text_sha1 = sha1(text.encode("utf-8")).hexdigest()

                process_ready(text_sha1, simhash64(text))

                if progress_every > 0 and idx % progress_every == 0:
                    print(f"processed_docs={idx}", flush=True)
        else:
            with ProcessPoolExecutor(max_workers=parallel_workers) as executor:
                for idx, row in enumerate(iter_jsonl(input_path), start=1):
                    if limit_docs is not None and idx > limit_docs:
                        break

                    total += 1

                    text = row.get("text")
                    if not isinstance(text, str):
                        continue
                    text = text.strip()

                    if len(text) < min_len:
                        too_short += 1
                        continue

                    text_sha1 = row.get("text_sha1")
                    if not isinstance(text_sha1, str) or not text_sha1:
                        text_sha1 = sha1(text.encode("utf-8")).hexdigest()

                    pending.append((text_sha1, executor.submit(simhash64_worker, text)))

                    while len(pending) >= max_pending:
                        psha1, pfut = pending.popleft()
                        process_ready(psha1, pfut.result())

                    if progress_every > 0 and idx % progress_every == 0:
                        print(f"processed_docs={idx}", flush=True)

                while pending:
                    psha1, pfut = pending.popleft()
                    process_ready(psha1, pfut.result())

        rows: List[Dict] = []
        for raw in engine.snapshot():
            near_dist = Counter({int(k): int(v) for k, v in raw["near_distance_distribution"].items()})
            near_p50 = percentile(near_dist, 0.50)
            near_p90 = percentile(near_dist, 0.90)
            near_p95 = percentile(near_dist, 0.95)
            dup_total = int(raw["exact_dup"]) + int(raw["near_dup"])

            rows.append(
                {
                    "threshold": int(raw["threshold"]),
                    "total": total,
                    "kept": int(raw["kept"]),
                    "exact_dup": int(raw["exact_dup"]),
                    "near_dup": int(raw["near_dup"]),
                    "too_short": too_short,
                    "duplicated_docs": dup_total,
                    "duplicated_rate_pct": pct(dup_total, total),
                    "near_p50": near_p50,
                    "near_p90": near_p90,
                    "near_p95": near_p95,
                    "near_distance_distribution": {str(k): near_dist[k] for k in sorted(near_dist)},
                }
            )

        rows.sort(key=lambda row: row["threshold"])
        recommended = choose_recommended(rows)
        return {
            "input": os.path.abspath(input_path),
            "bands": bands,
            "min_len": min_len,
            "thresholds": thresholds,
            "recommended_threshold": recommended,
            "results": rows,
        }

    states: Dict[int, State] = {t: State(bands) for t in thresholds}
    max_pending = max(1, parallel_workers * 8)
    pending: Deque[Tuple[str, str, Future[int]]] = deque()

    def process_text(doc_id: str, text_sha1: str, fp: int) -> None:
        for t in thresholds:
            st = states[t]
            if text_sha1 in st.seen_sha1:
                st.exact_dup += 1
                continue

            candidates: set[int] = set()
            keys = band_keys(fp, bands)
            for key in keys:
                for kept_idx in st.buckets.get(key, []):
                    candidates.add(kept_idx)

            is_near = False
            best_dist = None
            for kept_idx in candidates:
                dist = hamming_distance(fp, st.kept_fp[kept_idx])
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                if dist <= t:
                    is_near = True
                    break

            if is_near:
                st.near_dup += 1
                if best_dist is not None:
                    st.near_dist[best_dist] += 1
                continue

            keep_idx = len(st.kept_fp)
            st.seen_sha1.add(text_sha1)
            st.kept_doc_ids.append(doc_id)
            st.kept_sha1.append(text_sha1)
            st.kept_fp.append(fp)
            for key in keys:
                st.buckets[key].append(keep_idx)
            st.kept += 1

    if parallel_workers <= 1:
        for idx, row in enumerate(iter_jsonl(input_path), start=1):
            if limit_docs is not None and idx > limit_docs:
                break

            total += 1
            for st in states.values():
                st.total += 1

            text = row.get("text")
            if not isinstance(text, str):
                continue
            text = text.strip()

            if len(text) < min_len:
                too_short += 1
                for st in states.values():
                    st.too_short += 1
                continue

            doc_id = row.get("doc_id")
            if not isinstance(doc_id, str) or not doc_id:
                doc_id = f"doc_{idx}"

            text_sha1 = row.get("text_sha1")
            if not isinstance(text_sha1, str) or not text_sha1:
                text_sha1 = sha1(text.encode("utf-8")).hexdigest()

            process_text(doc_id, text_sha1, simhash64(text))

            if progress_every > 0 and idx % progress_every == 0:
                print(f"processed_docs={idx}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=parallel_workers) as executor:
            for idx, row in enumerate(iter_jsonl(input_path), start=1):
                if limit_docs is not None and idx > limit_docs:
                    break

                total += 1
                for st in states.values():
                    st.total += 1

                text = row.get("text")
                if not isinstance(text, str):
                    continue
                text = text.strip()

                if len(text) < min_len:
                    too_short += 1
                    for st in states.values():
                        st.too_short += 1
                    continue

                doc_id = row.get("doc_id")
                if not isinstance(doc_id, str) or not doc_id:
                    doc_id = f"doc_{idx}"

                text_sha1 = row.get("text_sha1")
                if not isinstance(text_sha1, str) or not text_sha1:
                    text_sha1 = sha1(text.encode("utf-8")).hexdigest()

                pending.append((doc_id, text_sha1, executor.submit(simhash64_worker, text)))

                while len(pending) >= max_pending:
                    pdoc_id, psha1, pfut = pending.popleft()
                    process_text(pdoc_id, psha1, pfut.result())

                if progress_every > 0 and idx % progress_every == 0:
                    print(f"processed_docs={idx}", flush=True)

            while pending:
                pdoc_id, psha1, pfut = pending.popleft()
                process_text(pdoc_id, psha1, pfut.result())

    rows: List[Dict] = []
    for t in thresholds:
        st = states[t]
        near_p50 = percentile(st.near_dist, 0.50)
        near_p90 = percentile(st.near_dist, 0.90)
        near_p95 = percentile(st.near_dist, 0.95)
        dup_total = st.exact_dup + st.near_dup

        rows.append(
            {
                "threshold": t,
                "total": st.total,
                "kept": st.kept,
                "exact_dup": st.exact_dup,
                "near_dup": st.near_dup,
                "too_short": st.too_short,
                "duplicated_docs": dup_total,
                "duplicated_rate_pct": pct(dup_total, st.total),
                "near_p50": near_p50,
                "near_p90": near_p90,
                "near_p95": near_p95,
                "near_distance_distribution": {str(k): st.near_dist[k] for k in sorted(st.near_dist)},
            }
        )

    recommended = choose_recommended(rows)
    summary = {
        "input": os.path.abspath(input_path),
        "bands": bands,
        "min_len": min_len,
        "thresholds": thresholds,
        "recommended_threshold": recommended,
        "results": rows,
    }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare multiple SimHash thresholds and generate a selection table."
    )
    parser.add_argument("--input", required=True, help="Input docs JSONL path")
    parser.add_argument(
        "--thresholds",
        default="2,3,4,5",
        help="Comma-separated thresholds to compare (default: 2,3,4,5)",
    )
    parser.add_argument(
        "--bands",
        type=int,
        default=4,
        help="Number of SimHash bands (must divide 64, default: 4)",
    )
    parser.add_argument(
        "--min-len",
        type=int,
        default=80,
        help="Ignore docs shorter than this (default: 80)",
    )
    parser.add_argument(
        "--limit-docs",
        type=int,
        default=None,
        help="Process only first N docs for quick test",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=20000,
        help="Progress print interval (default: 20000)",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=1,
        help="Number of worker processes for SimHash precompute (default: 1)",
    )
    parser.add_argument("--output-json", required=True, help="Output summary JSON path")
    parser.add_argument("--output-md", required=True, help="Output markdown table path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = parse_thresholds(args.thresholds)

    summary = sweep(
        input_path=args.input,
        thresholds=thresholds,
        bands=args.bands,
        min_len=args.min_len,
        limit_docs=args.limit_docs,
        progress_every=args.progress_every,
        parallel_workers=args.parallel_workers,
    )

    os.makedirs(os.path.dirname(args.output_json) or ".", exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    os.makedirs(os.path.dirname(args.output_md) or ".", exist_ok=True)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(build_markdown(summary))

    print(
        f"done: recommended_threshold={summary['recommended_threshold']} thresholds={thresholds}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
