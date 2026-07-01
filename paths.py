import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
HOTEL_DB_PATH = DATA_DIR / "hotel.db"
CHROMA_DB_DIR = PROJECT_ROOT / "chroma_db"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_sqlite_connection() -> sqlite3.Connection:
    """打开项目 data/ 目录下的 SQLite 数据库。"""
    ensure_data_dir()
    return sqlite3.connect(HOTEL_DB_PATH)
