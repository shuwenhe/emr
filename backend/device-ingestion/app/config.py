from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = BASE_DIR / "config"
MYSQL_CONFIG_PATH = CONFIG_DIR / "mysql.yaml"
CLICKHOUSE_CONFIG_PATH = CONFIG_DIR / "clickhouse.yaml"

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

EMR_DIR = DATA_DIR / "emr"
EMR_DIR.mkdir(parents=True, exist_ok=True)

REPORTS_DIR = Path("/Users/shuwen/hospital-report/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_mysql_config() -> dict:
	if not MYSQL_CONFIG_PATH.exists():
		raise FileNotFoundError(f"MySQL config not found: {MYSQL_CONFIG_PATH}")
	with MYSQL_CONFIG_PATH.open("r", encoding="utf-8") as f:
		payload = yaml.safe_load(f) or {}
	mysql_cfg = payload.get("mysql") or {}
	missing_keys = [
		key
		for key in ("host", "port", "database", "user", "password")
		if mysql_cfg.get(key) in (None, "")
	]
	if missing_keys:
		raise ValueError(
			"MySQL config missing required keys: " + ", ".join(missing_keys)
		)
	return {
		"host": mysql_cfg["host"],
		"port": int(mysql_cfg["port"]),
		"database": mysql_cfg["database"],
		"user": mysql_cfg["user"],
		"password": mysql_cfg["password"],
	}


_mysql = _load_mysql_config()
MYSQL_HOST = _mysql["host"]
MYSQL_PORT = _mysql["port"]
MYSQL_DB = _mysql["database"]
MYSQL_USER = _mysql["user"]
MYSQL_PASSWORD = _mysql["password"]


def _load_clickhouse_config() -> dict:
	if not CLICKHOUSE_CONFIG_PATH.exists():
		raise FileNotFoundError(f"ClickHouse config not found: {CLICKHOUSE_CONFIG_PATH}")
	with CLICKHOUSE_CONFIG_PATH.open("r", encoding="utf-8") as f:
		payload = yaml.safe_load(f) or {}
	ch_cfg = payload.get("clickhouse") or {}
	missing_keys = [
		key
		for key in ("host", "port", "database", "user")
		if ch_cfg.get(key) in (None, "")
	]
	if missing_keys:
		raise ValueError(
			"ClickHouse config missing required keys: " + ", ".join(missing_keys)
		)
	return {
		"host": ch_cfg["host"],
		"port": int(ch_cfg["port"]),
		"database": ch_cfg["database"],
		"user": ch_cfg["user"],
		"password": ch_cfg.get("password") or "",
	}


_clickhouse = _load_clickhouse_config()
CLICKHOUSE_HOST = _clickhouse["host"]
CLICKHOUSE_PORT = _clickhouse["port"]
CLICKHOUSE_DB = _clickhouse["database"]
CLICKHOUSE_USER = _clickhouse["user"]
CLICKHOUSE_PASSWORD = _clickhouse["password"]

MAX_FILE_MB = 200
ALLOWED_EXTENSIONS = {".bin", ".dat", ".npy", ".zip", ".csv", ".png", ".jpg", ".jpeg"}

DEVICE_DROP_DIR = Path("./device-drop")
DEVICE_DROP_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_PROCESSED_DIR = Path("./device-processed")
DEVICE_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_POLL_INTERVAL_SEC = 5
