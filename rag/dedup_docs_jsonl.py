#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import Future, ProcessPoolExecutor
from collections import Counter, defaultdict
from collections import deque
from hashlib import sha1
from typing import Deque, DefaultDict, Dict, Generator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Try to load the C++ SimHash extension for ~10-20x speedup.
# Falls back transparently to pure Python if the .so is not yet built.
# Build with:  make simhash-build
# ---------------------------------------------------------------------------
try:
    import importlib.util as _ilu
    import glob as _glob
    _rag_dir = os.path.dirname(__file__)
    _so_paths = []
    # Prefer rag/so layout, then fall back to older locations.
    _so_paths.extend(_glob.glob(os.path.join(_rag_dir, "so", "_simhash*.so")))
    _so_paths.extend(_glob.glob(os.path.join(_rag_dir, "_simhash*.so")))
    _so_paths.extend(_glob.glob(os.path.join(_rag_dir, "simhash", "_simhash*.so")))
    if _so_paths:
        _spec = _ilu.spec_from_file_location("_simhash", _so_paths[0])
        _simhash_ext = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_simhash_ext)       # type: ignore[union-attr]
        _USE_CPP = True
        _USE_CPP_DEDUP = hasattr(_simhash_ext, "DedupEngine")
        _USE_CPP_DEDUP_BATCH = _USE_CPP_DEDUP and hasattr(_simhash_ext.DedupEngine, "process_batch")
    else:
        _simhash_ext = None
        _USE_CPP = False
        _USE_CPP_DEDUP = False
        _USE_CPP_DEDUP_BATCH = False
except Exception:
    _simhash_ext = None
    _USE_CPP = False
    _USE_CPP_DEDUP = False
    _USE_CPP_DEDUP_BATCH = False


TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


def iter_jsonl(path: str) -> Generator[Tuple[int, Dict], None, None]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                yield line_no, json.loads(s)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc


def sha1_text(text: str) -> str:
    if _USE_CPP:
        return _simhash_ext.sha1_text(text)  # type: ignore[union-attr]
    return sha1(text.encode("utf-8")).hexdigest()


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

    weights = Counter(tokens)
    vec = [0] * 64
    for tok, w in weights.items():
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
    keys: List[Tuple[int, int]] = []
    for b in range(bands):
        keys.append((b, (fp >> (b * width)) & mask))
    return keys


def write_dup(
    dup_fh,
    dup_type: str,
    row: Dict,
    text_sha1_value: str,
    canonical_doc_id: str,
    canonical_sha1: str,
    fp: int,
    distance: Optional[int] = None,
) -> None:
    if dup_fh is None:
        return
    out = {
        "dup_type": dup_type,
        "doc_id": row.get("doc_id", ""),
        "canonical_doc_id": canonical_doc_id,
        "text_sha1": text_sha1_value,
        "canonical_text_sha1": canonical_sha1,
        "simhash64_hex": f"{fp:016x}",
        "distance": distance,
        "source": row.get("source", ""),
        "record_index": row.get("record_index"),
        "text_index": row.get("text_index"),
    }
    dup_fh.write(json.dumps(out, ensure_ascii=False) + "\n")


def dedup(
    input_path: str,
    output_path: str,
    dup_output_path: Optional[str],
    simhash_threshold: int,
    bands: int,
    min_len: int,
    limit_docs: Optional[int],
    progress_every: int,
    parallel_workers: int,
) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if dup_output_path:
        os.makedirs(os.path.dirname(dup_output_path) or ".", exist_ok=True)

    # Use the C++ DedupEngine when available — eliminates Python-level dict/set
    # overhead for seen_sha1, kept_fp, buckets on every processed record.
    if _USE_CPP_DEDUP:
        _engine = _simhash_ext.DedupEngine(bands, simhash_threshold)  # type: ignore[union-attr]
    else:
        _engine = None
        seen_sha1: set[str] = set()
        kept_doc_ids: List[str] = []
        kept_sha1: List[str] = []
        kept_fp: List[int] = []
        buckets: DefaultDict[Tuple[int, int], List[int]] = defaultdict(list)

    total = 0
    kept = 0
    exact_dup = 0
    near_dup = 0
    too_short = 0

    max_pending = max(1, parallel_workers * 8)
    pending: Deque[Tuple[Dict, str, str, Future[int]]] = deque()
    dedup_batch_size = int(os.getenv("RAG_DEDUP_DECISION_BATCH", "256"))
    dedup_batch_size = max(1, dedup_batch_size)

    def process_record(row: Dict, text: str, text_hash: str, fp: int, out_fh) -> None:
        nonlocal kept, exact_dup, near_dup

        if _engine is not None:
            # Fast path: all state lives in C++
            status, canonical_doc_id, canonical_sha1, dist = _engine.process(
                fp, text_hash, row.get("doc_id") or ""
            )
            if status == "exact":
                exact_dup += 1
                write_dup(dup_fh, "exact", row, text_hash,
                          canonical_doc_id="", canonical_sha1=text_hash, fp=0, distance=None)
                return
            if status == "near":
                near_dup += 1
                write_dup(dup_fh, "near", row, text_hash,
                          canonical_doc_id=canonical_doc_id,
                          canonical_sha1=canonical_sha1, fp=fp, distance=dist)
                return
            # status == "keep"
            doc_id = canonical_doc_id  # engine returns the assigned doc_id here
        else:
            # Pure-Python fallback path (no C++ DedupEngine built yet)
            if text_hash in seen_sha1:
                exact_dup += 1
                write_dup(
                    dup_fh, "exact", row, text_hash,
                    canonical_doc_id="", canonical_sha1=text_hash, fp=0, distance=None,
                )
                return

            candidates: set[int] = set()
            for key in band_keys(fp, bands):
                for idx in buckets.get(key, []):
                    candidates.add(idx)

            canonical_idx = -1
            canonical_dist = None
            for idx in candidates:
                dist = hamming_distance(fp, kept_fp[idx])
                if dist <= simhash_threshold:
                    canonical_idx = idx
                    canonical_dist = dist
                    break

            if canonical_idx >= 0:
                near_dup += 1
                write_dup(
                    dup_fh, "near", row, text_hash,
                    canonical_doc_id=kept_doc_ids[canonical_idx],
                    canonical_sha1=kept_sha1[canonical_idx],
                    fp=fp, distance=canonical_dist,
                )
                return

            seen_sha1.add(text_hash)
            doc_id = row.get("doc_id")
            if not isinstance(doc_id, str) or not doc_id:
                doc_id = f"doc_{kept}"

            idx = len(kept_fp)
            kept_doc_ids.append(doc_id)
            kept_sha1.append(text_hash)
            kept_fp.append(fp)
            for key in band_keys(fp, bands):
                buckets[key].append(idx)

        row["text"] = text
        row["text_sha1"] = text_hash
        row["simhash64_hex"] = f"{fp:016x}"
        row["dedup_stage"] = "deduped_doc"
        out_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        kept += 1

    def process_records_batch(records: List[Tuple[Dict, str, str, int]], out_fh) -> None:
        nonlocal kept, exact_dup, near_dup
        if not records:
            return
        if _engine is None:
            for row, text, text_hash, fp in records:
                process_record(row, text, text_hash, fp, out_fh)
            return

        if _USE_CPP_DEDUP_BATCH and len(records) > 1:
            fps = [fp for _, _, _, fp in records]
            text_hashes = [text_hash for _, _, text_hash, _ in records]
            doc_ids = [row.get("doc_id") or "" for row, _, _, _ in records]
            decisions = _engine.process_batch(fps, text_hashes, doc_ids)
            for (row, text, text_hash, fp), (status, canonical_doc_id, canonical_sha1, dist) in zip(records, decisions):
                if status == "exact":
                    exact_dup += 1
                    write_dup(
                        dup_fh, "exact", row, text_hash,
                        canonical_doc_id="", canonical_sha1=canonical_sha1, fp=0, distance=None,
                    )
                    continue
                if status == "near":
                    near_dup += 1
                    write_dup(
                        dup_fh, "near", row, text_hash,
                        canonical_doc_id=canonical_doc_id,
                        canonical_sha1=canonical_sha1, fp=fp, distance=dist,
                    )
                    continue

                row["text"] = text
                row["text_sha1"] = text_hash
                row["simhash64_hex"] = f"{fp:016x}"
                row["dedup_stage"] = "deduped_doc"
                out_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                kept += 1
            return

        for row, text, text_hash, fp in records:
            process_record(row, text, text_hash, fp, out_fh)

    dup_fh = open(dup_output_path, "w", encoding="utf-8") if dup_output_path else None
    try:
        with open(output_path, "w", encoding="utf-8") as out:
            if parallel_workers <= 1:
                decision_batch: List[Tuple[Dict, str, str, int]] = []
                for _, row in iter_jsonl(input_path):
                    if limit_docs is not None and total >= limit_docs:
                        break
                    total += 1

                    text = row.get("text")
                    if not isinstance(text, str):
                        continue
                    text = text.strip()
                    if len(text) < min_len:
                        too_short += 1
                        continue

                    text_hash = row.get("text_sha1")
                    if not isinstance(text_hash, str) or not text_hash:
                        text_hash = sha1_text(text)

                    decision_batch.append((row, text, text_hash, simhash64(text)))
                    if len(decision_batch) >= dedup_batch_size:
                        process_records_batch(decision_batch, out)
                        decision_batch.clear()

                    if progress_every > 0 and total % progress_every == 0:
                        print(
                            f"processed={total} kept={kept} exact_dup={exact_dup} near_dup={near_dup} too_short={too_short}",
                            file=sys.stderr,
                            flush=True,
                        )
                if decision_batch:
                    process_records_batch(decision_batch, out)
            else:
                with ProcessPoolExecutor(max_workers=parallel_workers) as executor:
                    decision_batch: List[Tuple[Dict, str, str, int]] = []
                    for _, row in iter_jsonl(input_path):
                        if limit_docs is not None and total >= limit_docs:
                            break
                        total += 1

                        text = row.get("text")
                        if not isinstance(text, str):
                            continue
                        text = text.strip()
                        if len(text) < min_len:
                            too_short += 1
                            continue

                        text_hash = row.get("text_sha1")
                        if not isinstance(text_hash, str) or not text_hash:
                            text_hash = sha1_text(text)

                        pending.append((row, text, text_hash, executor.submit(simhash64_worker, text)))

                        while len(pending) >= max_pending:
                            prow, ptext, psha1, pfut = pending.popleft()
                            decision_batch.append((prow, ptext, psha1, pfut.result()))
                            if len(decision_batch) >= dedup_batch_size:
                                process_records_batch(decision_batch, out)
                                decision_batch.clear()

                        if progress_every > 0 and total % progress_every == 0:
                            print(
                                f"processed={total} kept={kept} exact_dup={exact_dup} near_dup={near_dup} too_short={too_short}",
                                file=sys.stderr,
                                flush=True,
                            )

                    while pending:
                        prow, ptext, psha1, pfut = pending.popleft()
                        decision_batch.append((prow, ptext, psha1, pfut.result()))
                        if len(decision_batch) >= dedup_batch_size:
                            process_records_batch(decision_batch, out)
                            decision_batch.clear()
                    if decision_batch:
                        process_records_batch(decision_batch, out)
    finally:
        if dup_fh is not None:
            dup_fh.close()

    print(
        (
            "done: "
            f"input={input_path} output={output_path} "
            f"total={total} kept={kept} exact_dup={exact_dup} near_dup={near_dup} too_short={too_short}"
        ),
        file=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deduplicate docs JSONL using exact hash + SimHash near-duplicate detection."
    )
    parser.add_argument("--input", required=True, help="Input docs JSONL path")
    parser.add_argument("--output", required=True, help="Output deduplicated docs JSONL path")
    parser.add_argument(
        "--dup-output",
        default=None,
        help="Optional output JSONL for removed duplicates",
    )
    parser.add_argument(
        "--simhash-threshold",
        type=int,
        default=3,
        help="Hamming distance threshold for near duplicates (default: 3)",
    )
    parser.add_argument(
        "--bands",
        type=int,
        default=4,
        help="Number of SimHash bands for candidate retrieval, divisor of 64 (default: 4)",
    )
    parser.add_argument(
        "--min-len",
        type=int,
        default=80,
        help="Skip docs shorter than this length (default: 80)",
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
        default=10000,
        help="Print progress every N docs (default: 10000)",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=1,
        help="Number of worker processes for SimHash precompute (default: 1)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dedup(
        input_path=args.input,
        output_path=args.output,
        dup_output_path=args.dup_output,
        simhash_threshold=args.simhash_threshold,
        bands=args.bands,
        min_len=args.min_len,
        limit_docs=args.limit_docs,
        progress_every=args.progress_every,
        parallel_workers=args.parallel_workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
