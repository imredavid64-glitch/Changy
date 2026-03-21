from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


class DuckDb:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path

    def query(self, sql: str) -> tuple[list[str], list[list[Any]]]:
        conn = duckdb.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA threads=4;")
            rel = conn.execute(sql)
            desc = rel.description or []
            cols = [d[0] for d in desc]
            rows = [list(r) for r in rel.fetchall()]
            return cols, rows
        finally:
            conn.close()

