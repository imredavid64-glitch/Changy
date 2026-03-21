from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


DbKind = Literal["duckdb", "postgres", "mysql", "snowflake"]


@dataclass
class DbConnection:
    id: str
    kind: DbKind
    url: str
    engine: Engine


class ConnectorService:
    """
    Minimal DB connector registry (in-memory).

    URLs use SQLAlchemy formats:
    - Postgres: postgresql+psycopg://user:pass@host:5432/dbname
    - MySQL: mysql+pymysql://user:pass@host:3306/dbname
    - Snowflake (future): snowflake://...
    """

    def __init__(self) -> None:
        self._conns: dict[str, DbConnection] = {}

    def add(self, kind: DbKind, url: str) -> DbConnection:
        conn_id = uuid.uuid4().hex
        eng = create_engine(url, pool_pre_ping=True, future=True)
        conn = DbConnection(id=conn_id, kind=kind, url=url, engine=eng)
        self._conns[conn_id] = conn
        return conn

    def get(self, conn_id: str) -> DbConnection:
        conn = self._conns.get(conn_id)
        if not conn:
            raise KeyError("Connection not found")
        return conn

    def list(self) -> list[dict[str, Any]]:
        return [{"id": c.id, "kind": c.kind, "url": c.url} for c in self._conns.values()]

    def schema(self, conn_id: str) -> dict[str, Any]:
        conn = self.get(conn_id)
        insp = inspect(conn.engine)
        schemas = []
        try:
            schemas = list(insp.get_schema_names())
        except Exception:
            schemas = []

        tables: list[dict[str, Any]] = []
        for schema in (schemas or [None]):
            try:
                names = insp.get_table_names(schema=schema)
            except Exception:
                continue
            for t in names:
                try:
                    cols = insp.get_columns(t, schema=schema)
                except Exception:
                    cols = []
                tables.append(
                    {
                        "schema": schema,
                        "name": t,
                        "columns": [
                            {"name": c.get("name"), "type": str(c.get("type"))} for c in cols
                        ],
                    }
                )
        return {"schemas": schemas, "tables": tables}

    def query(self, conn_id: str, sql: str, limit: int = 5000) -> tuple[list[str], list[list[Any]]]:
        conn = self.get(conn_id)
        with conn.engine.connect() as c:
            res = c.execute(text(sql))
            rows = res.fetchmany(limit)
            cols = list(res.keys())
            return cols, [list(r) for r in rows]

