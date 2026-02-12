import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pymysql

from .config import MYSQL_DB, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def init_db() -> None:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    patient_id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(128),
                    gender VARCHAR(32),
                    age INT,
                    archived TINYINT DEFAULT 0,
                    payload_json JSON,
                    updated_at DATETIME
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    record_id VARCHAR(64) PRIMARY KEY,
                    patient_id VARCHAR(64),
                    created_at DATETIME,
                    data_path TEXT,
                    metadata_json JSON,
                    image_paths_json JSON,
                    INDEX idx_records_patient (patient_id),
                    CONSTRAINT fk_records_patient
                        FOREIGN KEY (patient_id)
                        REFERENCES patients(patient_id)
                        ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    record_id VARCHAR(64) PRIMARY KEY,
                    report_json JSON,
                    created_at DATETIME
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    record_id VARCHAR(64) PRIMARY KEY,
                    plan_json JSON,
                    created_at DATETIME
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS emrs (
                    emr_id VARCHAR(64) PRIMARY KEY,
                    record_id VARCHAR(64),
                    patient_id VARCHAR(64),
                    created_at DATETIME,
                    archived TINYINT DEFAULT 0,
                    emr_json JSON,
                    INDEX idx_emrs_patient (patient_id)
                )
                """
            )
            try:
                cursor.execute("ALTER TABLE emrs ADD COLUMN archived TINYINT DEFAULT 0")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE patients ADD COLUMN archived TINYINT DEFAULT 0")
            except Exception:
                pass


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def upsert_patient(patient: Dict[str, Any]) -> Optional[str]:
    patient_id = patient.get("patient_id")
    if not patient_id:
        return None
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
            """
            INSERT INTO patients (patient_id, name, gender, age, archived, payload_json, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name=VALUES(name),
                gender=VALUES(gender),
                age=VALUES(age),
                payload_json=VALUES(payload_json),
                updated_at=VALUES(updated_at)
            """,
            (
                patient_id,
                patient.get("name"),
                patient.get("gender"),
                patient.get("age"),
                0,
                json.dumps(patient, ensure_ascii=False),
                _now(),
            ),
            )
    return patient_id


def list_patients(
    limit: int = 100,
    offset: int = 0,
    include_archived: bool = False,
) -> List[Dict[str, Any]]:
    """Get all registered patients with pagination"""
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT patient_id, name, gender, age, archived, payload_json, updated_at
                FROM patients
                WHERE (%s = 1 OR archived = 0)
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
                """,
                (1 if include_archived else 0, limit, offset)
            )
            rows = cursor.fetchall()
            patients = []
            for row in rows:
                patient = json.loads(row["payload_json"]) if row.get("payload_json") else {}
                patient.update({
                    "patient_id": row["patient_id"],
                    "name": row["name"],
                    "gender": row["gender"],
                    "age": row["age"],
                    "archived": bool(row.get("archived")),
                    "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None
                })
                patients.append(patient)
            return patients


def get_patient(patient_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT patient_id, name, gender, age, archived, payload_json, updated_at
                FROM patients
                WHERE patient_id = %s
                """,
                (patient_id,)
            )
            row = cursor.fetchone()
    if not row:
        return None
    patient = json.loads(row.get("payload_json") or "{}")
    patient.update({
        "patient_id": row.get("patient_id"),
        "name": row.get("name"),
        "gender": row.get("gender"),
        "age": row.get("age"),
        "archived": bool(row.get("archived")),
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    })
    return patient


def update_patient(patient_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    current = get_patient(patient_id)
    if not current:
        return None
    merged = dict(current)
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    merged["patient_id"] = patient_id
    upsert_patient(merged)
    return get_patient(patient_id)


def archive_patient(patient_id: str, archived: bool = True) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE patients
                SET archived = %s, updated_at = %s
                WHERE patient_id = %s
                """,
                (1 if archived else 0, _now(), patient_id),
            )
    return get_patient(patient_id)


def delete_patient(patient_id: str) -> bool:
    """永久删除患者及其相关数据"""
    with _connect() as conn:
        with conn.cursor() as cursor:
            # 删除患者关联的EMR记录
            cursor.execute("DELETE FROM emrs WHERE patient_id = %s", (patient_id,))
            # 删除患者关联的采集记录
            cursor.execute("DELETE FROM records WHERE patient_id = %s", (patient_id,))
            # 删除患者
            cursor.execute("DELETE FROM patients WHERE patient_id = %s", (patient_id,))
            return cursor.rowcount > 0
    return False


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
        with conn.cursor() as cursor:
            cursor.execute(
            """
            INSERT INTO records (record_id, patient_id, created_at, data_path, metadata_json, image_paths_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                patient_id=VALUES(patient_id),
                created_at=VALUES(created_at),
                data_path=VALUES(data_path),
                metadata_json=VALUES(metadata_json),
                image_paths_json=VALUES(image_paths_json)
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
        with conn.cursor() as cursor:
            cursor.execute(
            """
            UPDATE records SET image_paths_json = %s WHERE record_id = %s
            """,
            (json.dumps(image_paths, ensure_ascii=False), record_id),
            )


def save_report(record_id: str, report: Dict[str, Any]) -> None:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
            """
            INSERT INTO reports (record_id, report_json, created_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                report_json=VALUES(report_json),
                created_at=VALUES(created_at)
            """,
            (record_id, json.dumps(report, ensure_ascii=False), _now()),
            )


def save_plan(record_id: str, plan: Dict[str, Any]) -> None:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
            """
            INSERT INTO plans (record_id, plan_json, created_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                plan_json=VALUES(plan_json),
                created_at=VALUES(created_at)
            """,
            (record_id, json.dumps(plan, ensure_ascii=False), _now()),
            )


def save_emr(emr: Dict[str, Any]) -> None:
    patient = emr.get("patient") or {}
    patient_id = upsert_patient(patient) if patient else None

    archived = 1 if emr.get("archived") else 0

    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
            """
            INSERT INTO emrs (emr_id, record_id, patient_id, created_at, archived, emr_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                record_id=VALUES(record_id),
                patient_id=VALUES(patient_id),
                created_at=VALUES(created_at),
                archived=VALUES(archived),
                emr_json=VALUES(emr_json)
            """,
            (
                emr.get("emr_id"),
                emr.get("record_id"),
                patient_id,
                emr.get("created_at") or _now(),
                archived,
                json.dumps(emr, ensure_ascii=False),
            ),
            )


def list_records(patient_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    query = "SELECT * FROM records"
    params: List[Any] = []
    if patient_id:
        query += " WHERE patient_id = %s"
        params.append(patient_id)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return [dict(row) for row in rows]


def list_emrs(
    patient_id: Optional[str] = None,
    limit: int = 50,
    include_archived: bool = False,
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM emrs"
    params: List[Any] = []
    where = []
    if patient_id:
        where.append("patient_id = %s")
        params.append(patient_id)
    if not include_archived:
        where.append("archived = 0")
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_emr_by_record_id(record_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT emr_json FROM emrs WHERE record_id = %s", (record_id,)
            )
            row = cursor.fetchone()
    if not row:
        return None
    return json.loads(row["emr_json"])


def get_report(record_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT report_json FROM reports WHERE record_id = %s", (record_id,)
            )
            row = cursor.fetchone()
    if not row:
        return None
    return json.loads(row["report_json"])


def get_patient_history(
    patient_id: str,
    exclude_record_id: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    query = (
        "SELECT r.record_id, r.created_at, r.data_path, r.image_paths_json, rep.report_json "
        "FROM records r "
        "LEFT JOIN reports rep ON rep.record_id = r.record_id "
        "WHERE r.patient_id = %s "
    )
    params: List[Any] = [patient_id]
    if exclude_record_id:
        query += "AND r.record_id <> %s "
        params.append(exclude_record_id)
    query += "ORDER BY r.created_at DESC LIMIT %s"
    params.append(limit)

    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    history: List[Dict[str, Any]] = []
    for row in rows:
        report_json = row.get("report_json")
        history.append(
            {
                "record_id": row.get("record_id"),
                "created_at": row.get("created_at"),
                "data_path": row.get("data_path"),
                "image_paths": json.loads(row.get("image_paths_json") or "[]"),
                "report": json.loads(report_json) if report_json else None,
            }
        )

    return history


def summary() -> Dict[str, Any]:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS cnt FROM patients")
            patients = cursor.fetchone()["cnt"]
            cursor.execute("SELECT COUNT(*) AS cnt FROM records")
            records = cursor.fetchone()["cnt"]
            cursor.execute("SELECT COUNT(*) AS cnt FROM reports")
            reports = cursor.fetchone()["cnt"]
            cursor.execute("SELECT COUNT(*) AS cnt FROM emrs")
            emrs = cursor.fetchone()["cnt"]
    return {
        "patients": patients,
        "records": records,
        "reports": reports,
        "emrs": emrs,
    }
