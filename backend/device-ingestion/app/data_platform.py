import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import PLATFORM_DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(PLATFORM_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    PLATFORM_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                name TEXT,
                gender TEXT,
                age INTEGER,
                payload_json TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                patient_id TEXT,
                created_at TEXT,
                data_path TEXT,
                metadata_json TEXT,
                image_paths_json TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                record_id TEXT PRIMARY KEY,
                report_json TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS plans (
                record_id TEXT PRIMARY KEY,
                plan_json TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS emrs (
                emr_id TEXT PRIMARY KEY,
                record_id TEXT,
                patient_id TEXT,
                created_at TEXT,
                emr_json TEXT
            );
            """
        )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def upsert_patient(patient: Dict[str, Any]) -> Optional[str]:
    patient_id = patient.get("patient_id")
    if not patient_id:
        return None
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO patients (patient_id, name, gender, age, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(patient_id) DO UPDATE SET
                name=excluded.name,
                gender=excluded.gender,
                age=excluded.age,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                patient_id,
                patient.get("name"),
                patient.get("gender"),
                patient.get("age"),
                json.dumps(patient, ensure_ascii=False),
                _now(),
            ),
        )
    return patient_id


def save_record(
    record_id: str,
    metadata: Dict[str, Any],
    data_path: str,
    image_paths: Optional[List[str]] = None,
) -> None:
    patient = metadata.get("patient") or {}
    patient_id = upsert_patient(patient)
    created_at = (metadata.get("capture") or {}).get("capture_time") or _now()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO records (record_id, patient_id, created_at, data_path, metadata_json, image_paths_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                patient_id=excluded.patient_id,
                created_at=excluded.created_at,
                data_path=excluded.data_path,
                metadata_json=excluded.metadata_json,
                image_paths_json=excluded.image_paths_json
            """,
            (
                record_id,
                patient_id,
                created_at,
                data_path,
                json.dumps(metadata, ensure_ascii=False),
                json.dumps(image_paths or [], ensure_ascii=False),
            ),
        )


def update_record_images(record_id: str, image_paths: List[str]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE records SET image_paths_json = ? WHERE record_id = ?
            """,
            (json.dumps(image_paths, ensure_ascii=False), record_id),
        )


def save_report(record_id: str, report: Dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO reports (record_id, report_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                report_json=excluded.report_json,
                created_at=excluded.created_at
            """,
            (record_id, json.dumps(report, ensure_ascii=False), _now()),
        )


def save_plan(record_id: str, plan: Dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO plans (record_id, plan_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                plan_json=excluded.plan_json,
                created_at=excluded.created_at
            """,
            (record_id, json.dumps(plan, ensure_ascii=False), _now()),
        )


def save_emr(emr: Dict[str, Any]) -> None:
    patient = emr.get("patient") or {}
    patient_id = upsert_patient(patient) if patient else None

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO emrs (emr_id, record_id, patient_id, created_at, emr_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(emr_id) DO UPDATE SET
                record_id=excluded.record_id,
                patient_id=excluded.patient_id,
                created_at=excluded.created_at,
                emr_json=excluded.emr_json
            """,
            (
                emr.get("emr_id"),
                emr.get("record_id"),
                patient_id,
                emr.get("created_at") or _now(),
                json.dumps(emr, ensure_ascii=False),
            ),
        )


def list_records(patient_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    query = "SELECT * FROM records"
    params: List[Any] = []
    if patient_id:
        query += " WHERE patient_id = ?"
        params.append(patient_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_emrs(patient_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    query = "SELECT * FROM emrs"
    params: List[Any] = []
    if patient_id:
        query += " WHERE patient_id = ?"
        params.append(patient_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_report(record_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT report_json FROM reports WHERE record_id = ?", (record_id,)
        ).fetchone()
    if not row:
        return None
    return json.loads(row["report_json"])


def summary() -> Dict[str, Any]:
    with _connect() as conn:
        patients = conn.execute("SELECT COUNT(*) AS cnt FROM patients").fetchone()[0]
        records = conn.execute("SELECT COUNT(*) AS cnt FROM records").fetchone()[0]
        reports = conn.execute("SELECT COUNT(*) AS cnt FROM reports").fetchone()[0]
        emrs = conn.execute("SELECT COUNT(*) AS cnt FROM emrs").fetchone()[0]
    return {
        "patients": patients,
        "records": records,
        "reports": reports,
        "emrs": emrs,
    }
