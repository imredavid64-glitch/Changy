from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .connectors import ConnectorService
from .db import DuckDb


class AssistantService:
    def __init__(self, data_dir: Path, local_db: DuckDb, connectors: ConnectorService) -> None:
        self.data_dir = data_dir
        self.local_db = local_db
        self.connectors = connectors
        from openai import OpenAI

        self.client = OpenAI()

    def _tool_instructions(self) -> str:
        return (
            "You can call tools by returning ONLY strict JSON in one line.\n"
            "Supported tool request shapes:\n"
            '{"tool":"run_sql","query":"select 1","target":"local|connection:<id>"}\n'
            '{"tool":"inspect_schema","target":"local|connection:<id>"}\n'
            '{"tool":"edit_file","path":"relative/path.txt","content":"full new contents"}\n'
            '{"tool":"none","response":"final user-facing reply"}\n'
            "If unsure, use tool=none."
        )

    def _run_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        name = tool.get("tool")
        target = str(tool.get("target", "local"))
        if name == "run_sql":
            query = str(tool.get("query", ""))
            if target == "local":
                cols, rows = self.local_db.query(query)
                return {"columns": cols, "rows": rows[:500]}
            if target.startswith("connection:"):
                conn_id = target.split(":", 1)[1]
                cols, rows = self.connectors.query(conn_id, query, limit=500)
                return {"columns": cols, "rows": rows}
            raise ValueError("Unknown target")

        if name == "inspect_schema":
            if target == "local":
                return {
                    "schemas": ["main"],
                    "tables": self.local_db.query(
                        "select table_name from information_schema.tables where table_schema='main';"
                    )[1],
                }
            if target.startswith("connection:"):
                conn_id = target.split(":", 1)[1]
                return self.connectors.schema(conn_id)
            raise ValueError("Unknown target")

        if name == "edit_file":
            rel_path = str(tool.get("path", "")).strip()
            if not rel_path or rel_path.startswith("/") or ".." in rel_path:
                raise ValueError("Invalid path")
            full_path = (Path.cwd() / rel_path).resolve()
            if not str(full_path).startswith(str(Path.cwd().resolve())):
                raise ValueError("Path escapes workspace")
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(str(tool.get("content", "")), encoding="utf-8")
            return {"ok": True, "path": rel_path}

        return {"skipped": True}

    def chat(self, messages: list[dict[str, str]]) -> str:
        sys = (
            "You are Changy assistant for Python, R, SQL, and data engineering.\n"
            + self._tool_instructions()
        )
        first = self.client.responses.create(
            model="gpt-4.1-mini",
            input=[{"role": "system", "content": sys}, *messages],
        )
        raw = (first.output_text or "").strip()
        try:
            tool_req = json.loads(raw)
        except Exception:
            return raw or "I could not produce a response."

        if tool_req.get("tool") in {"run_sql", "inspect_schema", "edit_file"}:
            tool_result = self._run_tool(tool_req)
            second = self.client.responses.create(
                model="gpt-4.1-mini",
                input=[
                    {"role": "system", "content": "Respond helpfully to user using tool result."},
                    *messages,
                    {"role": "assistant", "content": json.dumps(tool_req)},
                    {"role": "tool", "content": json.dumps(tool_result)},
                ],
            )
            return second.output_text or "Done."

        return str(tool_req.get("response", raw))

