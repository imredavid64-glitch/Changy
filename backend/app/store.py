from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from .models import Notebook, NotebookCell


class NotebookStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, notebook_id: str) -> Path:
        return self.root_dir / f"{notebook_id}.json"

    def list(self) -> list[Notebook]:
        items: list[Notebook] = []
        for p in sorted(self.root_dir.glob("*.json"), key=lambda x: x.name):
            try:
                items.append(self.get(p.stem))
            except Exception:
                continue
        return items

    def get(self, notebook_id: str) -> Notebook:
        p = self._path_for(notebook_id)
        data = json.loads(p.read_text(encoding="utf-8"))
        return Notebook.model_validate(data)

    def create(self, title: str) -> Notebook:
        notebook_id = uuid.uuid4().hex
        nb = Notebook(
            id=notebook_id,
            title=title,
            cells=[
                NotebookCell(
                    id=uuid.uuid4().hex,
                    language="sql",
                    content="select 1 as hello;",
                )
            ],
        )
        self.put(nb)
        return nb

    def put(self, notebook: Notebook) -> Notebook:
        p = self._path_for(notebook.id)

        tmp = Path(f"{p}.tmp")
        tmp.write_text(
            json.dumps(notebook.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, p)
        return notebook

