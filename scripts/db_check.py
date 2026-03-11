from pathlib import Path
import sys

import pymysql
import yaml


def load_mysql_config() -> dict:
    root = Path(__file__).resolve().parents[2]
    config_path = root / "config" / "mysql.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"MySQL config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    mysql_cfg = payload.get("mysql") or {}
    required = ("host", "port", "database", "user", "password")
    missing = [k for k in required if mysql_cfg.get(k) in (None, "")]
    if missing:
        raise ValueError("MySQL config missing required keys: " + ", ".join(missing))

    return {
        "host": mysql_cfg["host"],
        "port": int(mysql_cfg["port"]),
        "database": mysql_cfg["database"],
        "user": mysql_cfg["user"],
        "password": mysql_cfg["password"],
    }


def main() -> int:
    cfg = load_mysql_config()
    connection = None
    try:
        connection = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            autocommit=True,
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        print(
            f"MySQL check passed: {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
        )
        return 0
    except Exception as exc:
        print(f"MySQL check failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
