import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("FEE_DB_PATH", ROOT / "data" / "processed" / "fees.db"))


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    if not p.exists():
        raise FileNotFoundError(f"DB가 없습니다: {p}. 먼저 `python -m etl.build_db` 를 실행하세요.")
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con
