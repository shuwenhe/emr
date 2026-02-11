from pathlib import Path

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

EMR_DIR = DATA_DIR / "emr"
EMR_DIR.mkdir(parents=True, exist_ok=True)

REPORTS_DIR = Path("./reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_DB = "hospital"
MYSQL_USER = "hospital"
MYSQL_PASSWORD = "hospital"

MAX_FILE_MB = 200
ALLOWED_EXTENSIONS = {".bin", ".dat", ".npy", ".zip", ".csv", ".png", ".jpg", ".jpeg"}

DEVICE_DROP_DIR = Path("./device-drop")
DEVICE_DROP_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_PROCESSED_DIR = Path("./device-processed")
DEVICE_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_POLL_INTERVAL_SEC = 5
