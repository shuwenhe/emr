from pathlib import Path

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_MB = 200
ALLOWED_EXTENSIONS = {".bin", ".dat", ".npy", ".zip", ".csv"}
