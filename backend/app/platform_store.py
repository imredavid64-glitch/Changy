from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


class JsonEntityStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, entity_id: str) -> Path:
        return self.root / f"{entity_id}.json"

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for p in sorted(self.root.glob("*.json"), key=lambda x: x.name):
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return items

    def get(self, entity_id: str) -> dict[str, Any]:
        return json.loads(self._path(entity_id).read_text(encoding="utf-8"))

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {**payload}
        payload.setdefault("id", uuid.uuid4().hex)
        self.put(payload)
        return payload

    def put(self, payload: dict[str, Any]) -> dict[str, Any]:
        entity_id = payload["id"]
        path = self._path(entity_id)
        tmp = Path(f"{path}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return payload

