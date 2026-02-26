#!/usr/bin/env python3
"""Convert raw infrared radiance signal values to temperature (°C).

This script expects radiometric RAW values (typically 14/16-bit) and
camera calibration constants (R, B, F, O) from the device/SDK.

Formula (FLIR-style):
  radiance = (raw - O) / R
  T(K) = B / ln(R / radiance + F)

Optional emissivity correction using reflected temperature:
  radiance_obj = (radiance - (1-ε) * radiance_reflected) / ε
  radiance_reflected = R / (exp(B / TrefK) - F)
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable, List, Optional


def _parse_row(values: Iterable[str]) -> List[float]:
    parsed: List[float] = []
    for value in values:
        value = value.strip()
        if not value:
            continue
        parsed.append(float(value))
    return parsed


def _radiance_from_raw(raw: float, r: float, o: float) -> float:
    return (raw - o) / r


def _radiance_from_temp_k(temp_k: float, r: float, b: float, f: float) -> float:
    return r / (math.exp(b / temp_k) - f)


def _temp_k_from_radiance(radiance: float, r: float, b: float, f: float) -> Optional[float]:
    if radiance <= 0:
        return None
    try:
        return b / math.log(r / radiance + f)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def convert_matrix(
    rows: List[List[float]],
    r: float,
    b: float,
    f: float,
    o: float,
    emissivity: float,
    reflected_temp_c: float,
) -> List[List[Optional[float]]]:
    reflected_k = reflected_temp_c + 273.15
    radiance_reflected = _radiance_from_temp_k(reflected_k, r, b, f)

    output: List[List[Optional[float]]] = []
    for row in rows:
        out_row: List[Optional[float]] = []
        for raw in row:
            radiance = _radiance_from_raw(raw, r, o)
            if emissivity > 0 and emissivity < 1:
                radiance = (radiance - (1 - emissivity) * radiance_reflected) / emissivity
            temp_k = _temp_k_from_radiance(radiance, r, b, f)
            if temp_k is None:
                out_row.append(None)
            else:
                out_row.append(round(temp_k - 273.15, 2))
        output.append(out_row)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert raw IR radiance to temperature.")
    parser.add_argument("--input", required=True, help="Input CSV file (raw values)")
    parser.add_argument("--output", required=True, help="Output CSV file (temperature °C)")
    parser.add_argument("--r", type=float, required=True, help="Calibration constant R")
    parser.add_argument("--b", type=float, required=True, help="Calibration constant B")
    parser.add_argument("--f", type=float, required=True, help="Calibration constant F")
    parser.add_argument("--o", type=float, required=True, help="Calibration constant O")
    parser.add_argument("--emissivity", type=float, default=0.98, help="Emissivity (default 0.98)")
    parser.add_argument(
        "--reflected-temp-c",
        type=float,
        default=25.0,
        help="Reflected/ambient temperature in °C (default 25.0)",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    rows: List[List[float]] = []
    with input_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            rows.append(_parse_row(row))

    temps = convert_matrix(
        rows,
        r=args.r,
        b=args.b,
        f=args.f,
        o=args.o,
        emissivity=args.emissivity,
        reflected_temp_c=args.reflected_temp_c,
    )

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in temps:
            writer.writerow(["" if value is None else f"{value:.2f}" for value in row])


if __name__ == "__main__":
    main()
