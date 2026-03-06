import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

from clickhouse_driver import Client
import numpy as np

from .config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
)

_TABLE_NAME = "thermal_timeseries"


def _connect(database: Optional[str] = None) -> Client:
    return Client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        user=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database=database or CLICKHOUSE_DB,
    )


def _validate_identifier(value: str) -> None:
    safe = value.replace("_", "").isalnum()
    if not safe:
        raise ValueError(f"Invalid identifier: {value}")


def _ensure_schema() -> None:
    _validate_identifier(CLICKHOUSE_DB)
    _validate_identifier(_TABLE_NAME)
    admin = _connect(database="default")
    admin.execute(f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DB}")
    client = _connect()
    client.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {CLICKHOUSE_DB}.{_TABLE_NAME} (
            record_id String,
            device_id String,
            patient_id String,
            capture_time DateTime,
            frame_id String,
            row UInt16,
            col UInt16,
            temperature_c Float32,
            ingest_time DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        PARTITION BY toYYYYMM(capture_time)
        ORDER BY (record_id, frame_id, row, col)
        """
    )


def _parse_capture_time(raw: Optional[str]) -> datetime:
    if not raw:
        return datetime.now()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.now()


def _extract_ids(metadata: Dict) -> tuple[str, str]:
    device_id = ""
    patient_id = ""

    device = metadata.get("device") or {}
    if device:
        device_id = str(device.get("device_id") or "")

    if not device_id:
        device_id = str(metadata.get("device_id") or metadata.get("device") or "")

    patient = metadata.get("patient") or {}
    if patient:
        patient_id = str(patient.get("patient_id") or "")

    subject = metadata.get("subject") or {}
    if not patient_id and subject:
        patient_id = str(subject.get("patient_id") or "")

    return device_id, patient_id


def insert_thermal_csv(
    record_id: str,
    metadata: Dict,
    data_path: str,
    frame_id: str,
    batch_size: int = 5000,
) -> int:
    _ensure_schema()
    device_id, patient_id = _extract_ids(metadata)
    capture = metadata.get("capture") or {}
    capture_time = _parse_capture_time(capture.get("capture_time") or metadata.get("capture_time"))

    client = _connect()
    insert_sql = (
        f"INSERT INTO {_TABLE_NAME} "
        "(record_id, device_id, patient_id, capture_time, frame_id, row, col, temperature_c) "
        "VALUES"
    )

    total = 0
    batch: list[tuple] = []
    data_file = Path(data_path)

    def flush_batch() -> None:
        nonlocal total
        if batch:
            client.execute(insert_sql, batch)
            total += len(batch)
            batch.clear()

    with data_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        structured_csv = {"row", "col", "temperature_c"}.issubset(set(fieldnames))
        if structured_csv:
            for item in reader:
                try:
                    row = int(item["row"])
                    col = int(item["col"])
                    temp = float(item["temperature_c"])
                except (ValueError, KeyError):
                    continue

                batch.append(
                    (
                        record_id,
                        device_id,
                        patient_id,
                        capture_time,
                        frame_id,
                        row,
                        col,
                        temp,
                    )
                )
                if len(batch) >= batch_size:
                    flush_batch()
        else:
            # matrix CSV fallback (no headers): each row is a temperature row
            matrix = np.loadtxt(str(data_file), delimiter=",", dtype=np.float32)
            if matrix.ndim == 1:
                matrix = matrix.reshape(1, -1)
            if matrix.ndim != 2:
                raise ValueError("invalid_matrix_csv_shape")

            for r in range(matrix.shape[0]):
                for c in range(matrix.shape[1]):
                    temp = float(matrix[r, c])
                    batch.append(
                        (
                            record_id,
                            device_id,
                            patient_id,
                            capture_time,
                            frame_id,
                            int(r),
                            int(c),
                            temp,
                        )
                    )
                    if len(batch) >= batch_size:
                        flush_batch()

    flush_batch()

    return total
