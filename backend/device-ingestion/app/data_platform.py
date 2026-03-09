import json
import logging
import time
import zlib
import base64
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar

import pymysql
from pymysql.err import OperationalError
from dbutils.pooled_db import PooledDB

from .config import MYSQL_DB, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

logger = logging.getLogger(__name__)

_DB_RETRYABLE_ERROR_CODES = {2006, 2013, 2055}
_DB_MAX_RETRIES = 3
_DB_RETRY_BACKOFF_BASE = 0.5
_COMPRESSION_THRESHOLD_MB = 10  # Compress data larger than 10MB
_T = TypeVar("_T")

# Database connection pool
# mincached: minimum number of idle connections in the pool
# maxcached: maximum number of idle connections in the pool
# maxconnections: maximum number of connections overall
# blocking: wait if pool is exhausted (True) or raise exception (False)
_db_pool: Optional[PooledDB] = None

def _get_connection_pool() -> PooledDB:
    """Get or create the database connection pool."""
    global _db_pool
    if _db_pool is None:
        logger.info("Initializing MySQL connection pool")
        _db_pool = PooledDB(
            creator=pymysql,
            maxconnections=10,  # Maximum connections overall
            mincached=2,        # Keep at least 2 warm connections
            maxcached=5,        # Cache up to 5 idle connections
            blocking=True,      # Wait if pool exhausted
            ping=1,             # Check connections before use (1=default)
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=10,
            read_timeout=60,
            write_timeout=60,
        )
        logger.info("MySQL connection pool initialized successfully")
    return _db_pool

def _compress_data(data: str) -> str:
    """Compress data and return as base64-encoded string with marker prefix."""
    compressed = zlib.compress(data.encode('utf-8'), level=6)
    encoded = base64.b64encode(compressed).decode('ascii')
    return f"ZLIB_COMPRESSED:{encoded}"


def _decompress_data(data: str) -> str:
    """Decompress base64-encoded zlib data if marked, otherwise return as-is."""
    if isinstance(data, str) and data.startswith("ZLIB_COMPRESSED:"):
        encoded = data[16:]  # Remove prefix
        compressed = base64.b64decode(encoded)
        return zlib.decompress(compressed).decode('utf-8')
    return data


def _connect() -> pymysql.connections.Connection:
    """Get a connection from the pool."""
    pool = _get_connection_pool()
    conn = pool.connection()
    try:
        conn.ping(reconnect=False)
    except Exception:
        conn.close()
        raise
    return conn


def _is_retryable_operational_error(exc: OperationalError) -> bool:
    try:
        code = int(exc.args[0]) if exc.args else None
    except Exception:
        code = None
    return code in _DB_RETRYABLE_ERROR_CODES


def _run_db_op(fn: Callable[[pymysql.connections.Connection], _T]) -> _T:
    last_exc: Optional[Exception] = None
    for attempt in range(_DB_MAX_RETRIES + 1):
        conn = None
        try:
            conn = _connect()
            # Verify connection is alive before using it
            try:
                conn.ping(reconnect=True)
            except Exception as e:
                logger.warning(f"Connection ping failed: {e}")
                raise OperationalError(2006, "Connection not alive")
            
            result = fn(conn)
            conn.close()
            return result
        except OperationalError as exc:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            last_exc = exc
            if not _is_retryable_operational_error(exc) or attempt >= _DB_MAX_RETRIES:
                raise
            # Exponential backoff: 0.5s, 1s, 2s
            wait_time = _DB_RETRY_BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                "Retrying MySQL operation after OperationalError (attempt %d/%d, waiting %.1fs): %s",
                attempt + 1,
                _DB_MAX_RETRIES + 1,
                wait_time,
                exc,
            )
            time.sleep(wait_time)
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("database_operation_failed")


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
            try:
                cursor.execute("CREATE INDEX idx_emrs_record ON emrs (record_id)")
            except Exception:
                pass
            try:
                cursor.execute("CREATE INDEX idx_emrs_created ON emrs (created_at)")
            except Exception:
                pass
            try:
                cursor.execute("CREATE INDEX idx_emrs_archived_created ON emrs (archived, created_at)")
            except Exception:
                pass
            try:
                cursor.execute("CREATE INDEX idx_emrs_patient_archived_created ON emrs (patient_id, archived, created_at)")
            except Exception:
                pass


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def upsert_patient(patient: Dict[str, Any]) -> Optional[str]:
    patient_id = patient.get("patient_id")
    if not patient_id:
        return None
    def _op(conn: pymysql.connections.Connection) -> None:
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
    _run_db_op(_op)
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
    report_json = json.dumps(report, ensure_ascii=False, default=str)
    report_size_mb = len(report_json.encode('utf-8')) / (1024 * 1024)
    logger.info(f"Saving report for {record_id}, size: {report_size_mb:.2f} MB")
    
    # Compress if larger than threshold
    if report_size_mb > _COMPRESSION_THRESHOLD_MB:
        logger.info(f"Compressing report ({report_size_mb:.2f} MB) for {record_id}")
        compressed = _compress_data(report_json)
        # Wrap compressed string as JSON string to satisfy JSON column validation
        report_json = json.dumps(compressed, ensure_ascii=False)
        compressed_size_mb = len(report_json.encode('utf-8')) / (1024 * 1024)
        logger.info(f"Compressed report size: {compressed_size_mb:.2f} MB (ratio: {compressed_size_mb/report_size_mb*100:.1f}%)")
    
    def _op(conn: pymysql.connections.Connection) -> None:
        with conn.cursor() as cursor:
            cursor.execute(
            """
            INSERT INTO reports (record_id, report_json, created_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                report_json=VALUES(report_json),
                created_at=VALUES(created_at)
            """,
            (record_id, report_json, _now()),
            )
    _run_db_op(_op)


def save_plan(record_id: str, plan: Dict[str, Any]) -> None:
    def _op(conn: pymysql.connections.Connection) -> None:
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
    _run_db_op(_op)


def save_emr(emr: Dict[str, Any]) -> None:
    patient = emr.get("patient") or {}
    patient_id = upsert_patient(patient) if patient else None
    record_id = emr.get("record_id")

    if not patient_id and record_id:
        def _resolve_patient_id(conn: pymysql.connections.Connection) -> Optional[str]:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT patient_id FROM records WHERE record_id = %s LIMIT 1",
                    (record_id,),
                )
                row = cursor.fetchone()
            return row.get("patient_id") if row else None

        patient_id = _run_db_op(_resolve_patient_id)
        if patient_id:
            logger.info("Resolved missing EMR patient_id from record %s -> %s", record_id, patient_id)

    archived = 1 if emr.get("archived") else 0
    if not patient_id:
        archived = 1
        logger.warning(
            "EMR %s has no resolvable patient_id (record_id=%s); archiving to avoid orphan active data",
            emr.get("emr_id"),
            record_id,
        )
    
    # Prepare EMR JSON with compression for large data
    emr_json = json.dumps(emr, ensure_ascii=False, default=str)
    emr_size_mb = len(emr_json.encode('utf-8')) / (1024 * 1024)
    logger.info(f"Saving EMR {emr.get('emr_id')}, size: {emr_size_mb:.2f} MB")
    
    # Compress if larger than threshold
    if emr_size_mb > _COMPRESSION_THRESHOLD_MB:
        logger.info(f"Compressing EMR ({emr_size_mb:.2f} MB) {emr.get('emr_id')}")
        compressed = _compress_data(emr_json)
        # Wrap compressed string as JSON string to satisfy JSON column validation
        emr_json = json.dumps(compressed, ensure_ascii=False)
        compressed_size_mb = len(emr_json.encode('utf-8')) / (1024 * 1024)
        logger.info(f"Compressed EMR size: {compressed_size_mb:.2f} MB (ratio: {compressed_size_mb/emr_size_mb*100:.1f}%)")

    def _op(conn: pymysql.connections.Connection) -> None:
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
                record_id,
                patient_id,
                emr.get("created_at") or _now(),
                archived,
                emr_json,
            ),
            )
    _run_db_op(_op)


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
    record_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    ✅ 优化：两步查询避免排序缓冲区溢出
    步骤1：只查询小字段用于排序（emr_id, created_at, archived）
    步骤2：根据ID批量获取完整数据
    这样 ORDER BY 只处理小数据，不会导致 MySQL sort buffer 溢出
    """
    results: List[Dict[str, Any]] = []
    where: List[str] = []
    params: List[Any] = []

    if record_id:
        where.append("record_id = %s")
        params.append(record_id)
        # For single record query, use direct approach
        with _connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT emr_id, record_id, patient_id, created_at, archived, emr_json "
                    f"FROM emrs WHERE record_id = %s LIMIT 1",
                    (record_id,),
                )
                row = cursor.fetchone()
        
        if not row:
            return []
        
        if row.get("emr_json"):
            try:
                emr_data = json.loads(row["emr_json"])
                if isinstance(emr_data, str):
                    emr_data = _decompress_data(emr_data)
                    emr_data = json.loads(emr_data)
                return [emr_data]
            except (json.JSONDecodeError, TypeError):
                return [dict(row)]
        else:
            return [dict(row)]
    
    # 多记录查询：两步避免排序缓冲溢出
    if patient_id:
        where.append("patient_id = %s")
        params.append(patient_id)
    if not include_archived:
        where.append("archived = 0")

    where_clause = f" WHERE {' AND '.join(where)}" if where else ""
    
    # ✅ 步骤1：只查询必要的小字段用于排序和获取ID
    # 不包含大的emr_json字段，避免排序缓冲区溢出
    id_params = list(params)
    id_params.append(limit)
    
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT emr_id, created_at "
                f"FROM emrs{where_clause} "
                "ORDER BY created_at DESC LIMIT %s",
                id_params,
            )
            id_rows = cursor.fetchall()
    
    if not id_rows:
        return []
    
    emr_ids = [row["emr_id"] for row in id_rows]
    
    # ✅ 步骤2：根据ID列表批量获取完整数据
    # 由于已经排过序，直接按ID顺序获取即可
    placeholders = ", ".join(["%s"] * len(emr_ids))
    
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT emr_id, record_id, patient_id, created_at, archived, emr_json "
                f"FROM emrs WHERE emr_id IN ({placeholders})",
                emr_ids,
            )
            data_rows = cursor.fetchall()
    
    # 按原始排序顺序返回
    row_map = {row["emr_id"]: row for row in data_rows}
    ordered_rows = [row_map[emr_id] for emr_id in emr_ids if emr_id in row_map]
    
    for row in ordered_rows:
        if row.get("emr_json"):
            try:
                emr_data = json.loads(row["emr_json"])
                if isinstance(emr_data, str):
                    emr_data = _decompress_data(emr_data)
                    emr_data = json.loads(emr_data)
                results.append(emr_data)
            except (json.JSONDecodeError, TypeError):
                results.append(dict(row))
        else:
            results.append(dict(row))
    
    return results


def get_emr_by_record_id(record_id: str) -> Optional[Dict[str, Any]]:
    def _op(conn: pymysql.connections.Connection) -> Optional[Dict[str, Any]]:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT emr_json FROM emrs WHERE record_id = %s", (record_id,)
            )
            row = cursor.fetchone()
        if not row:
            return None
        
        # Parse JSON (handles both uncompressed objects and compressed strings)
        result = json.loads(row["emr_json"])
        
        # If it's a string (compressed), decompress it then parse
        if isinstance(result, str):
            result = _decompress_data(result)
            result = json.loads(result)
        
        return result
    return _run_db_op(_op)


def get_report(record_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT report_json FROM reports WHERE record_id = %s", (record_id,)
            )
            row = cursor.fetchone()
    if not row:
        return None
    
    # Parse JSON (handles both uncompressed objects and compressed strings)
    result = json.loads(row["report_json"])
    
    # If it's a string (compressed), decompress it then parse
    if isinstance(result, str):
        result = _decompress_data(result)
        result = json.loads(result)
    
    return result


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
        report_data = None
        if report_json:
            # Parse JSON (handles both uncompressed objects and compressed strings)
            parsed = json.loads(report_json)
            # If it's a string (compressed), decompress it then parse
            if isinstance(parsed, str):
                parsed = _decompress_data(parsed)
                parsed = json.loads(parsed)
            report_data = parsed
        
        history.append(
            {
                "record_id": row.get("record_id"),
                "created_at": row.get("created_at"),
                "data_path": row.get("data_path"),
                "image_paths": json.loads(row.get("image_paths_json") or "[]"),
                "report": report_data,
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
