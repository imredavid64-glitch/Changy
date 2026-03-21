from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .assistant import AssistantService
from .connectors import ConnectorService
from .db import DuckDb
from .kernels import KernelService
from .models import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantMessage,
    DbConnectRequest,
    DbConnectResponse,
    DbQueryRequest,
    DbSchemaResponse,
    KernelExecuteRequest,
    KernelExecuteResponse,
    KernelStartRequest,
    KernelStartResponse,
    Notebook,
    NotebookCreateRequest,
    NotebookUpdateRequest,
    SqlQueryRequest,
    SqlQueryResponse,
)
from .platform_store import JsonEntityStore
from .store import NotebookStore


DATA_DIR = Path(__file__).resolve().parents[1] / ".data"

app = FastAPI(title="Changy Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = NotebookStore(DATA_DIR / "notebooks")
db = DuckDb(DATA_DIR / "local.duckdb")
kernels = KernelService()
connectors = ConnectorService()
datasets = JsonEntityStore(DATA_DIR / "datasets")
experiments = JsonEntityStore(DATA_DIR / "experiments")
training_jobs = JsonEntityStore(DATA_DIR / "training_jobs")
assistant: AssistantService | None = None
if os.getenv("OPENAI_API_KEY"):
    assistant = AssistantService(DATA_DIR, db, connectors)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sql/query", response_model=SqlQueryResponse)
def run_sql(req: SqlQueryRequest) -> SqlQueryResponse:
    try:
        cols, rows = db.query(req.query)
        return SqlQueryResponse(columns=cols, rows=rows)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/db/connections")
def list_db_connections() -> list[dict[str, str]]:
    return connectors.list()


@app.post("/db/connect", response_model=DbConnectResponse)
def db_connect(req: DbConnectRequest) -> DbConnectResponse:
    try:
        conn = connectors.add(req.kind, req.url)
        return DbConnectResponse(id=conn.id, kind=conn.kind, url=conn.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/db/{connection_id}/schema", response_model=DbSchemaResponse)
def db_schema(connection_id: str) -> DbSchemaResponse:
    try:
        return DbSchemaResponse.model_validate(connectors.schema(connection_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Connection not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/db/query", response_model=SqlQueryResponse)
def db_query(req: DbQueryRequest) -> SqlQueryResponse:
    try:
        cols, rows = connectors.query(req.connection_id, req.query, limit=req.limit)
        return SqlQueryResponse(columns=cols, rows=rows)
    except KeyError:
        raise HTTPException(status_code=404, detail="Connection not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/kernels/start", response_model=KernelStartResponse)
def start_kernel(req: KernelStartRequest) -> KernelStartResponse:
    try:
        sess = kernels.start(req.language)
        return KernelStartResponse(kernel_id=sess.id, language=sess.language)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/kernels/execute", response_model=KernelExecuteResponse)
def execute_kernel(req: KernelExecuteRequest) -> KernelExecuteResponse:
    # Supports both:
    # - stateful execution (kernel_id provided)
    # - stateless execution (language provided; temp kernel spun up and torn down)
    if req.kernel_id is None and req.language is None:
        raise HTTPException(status_code=400, detail="Provide kernel_id or language")

    temp_id: str | None = None
    try:
        kernel_id = req.kernel_id
        if kernel_id is None:
            sess = kernels.start(req.language)  # type: ignore[arg-type]
            temp_id = sess.id
            kernel_id = sess.id

        out = kernels.execute(kernel_id, req.code, timeout_s=req.timeout_s)
        return KernelExecuteResponse.model_validate(out)
    except KeyError:
        raise HTTPException(status_code=404, detail="Kernel not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if temp_id is not None:
            kernels.stop(temp_id)


@app.get("/notebooks", response_model=list[Notebook])
def list_notebooks() -> list[Notebook]:
    return store.list()


@app.post("/notebooks", response_model=Notebook)
def create_notebook(req: NotebookCreateRequest) -> Notebook:
    return store.create(req.title)


@app.get("/notebooks/{notebook_id}", response_model=Notebook)
def get_notebook(notebook_id: str) -> Notebook:
    try:
        return store.get(notebook_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")


@app.put("/notebooks/{notebook_id}", response_model=Notebook)
def update_notebook(notebook_id: str, req: NotebookUpdateRequest) -> Notebook:
    try:
        nb = store.get(notebook_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")

    data = nb.model_dump()
    if req.title is not None:
        data["title"] = req.title
    if req.cells is not None:
        data["cells"] = [c.model_dump() for c in req.cells]

    updated = Notebook.model_validate(data)
    store.put(updated)
    return updated


@app.post("/assistant/chat", response_model=AssistantChatResponse)
def assistant_chat(req: AssistantChatRequest) -> AssistantChatResponse:
    if assistant is None:
        content = (
            "OPENAI_API_KEY is not set, so assistant runs in fallback mode.\n"
            "Set OPENAI_API_KEY and restart backend to enable tool-capable LLM chat."
        )
        return AssistantChatResponse(
            message=AssistantMessage(role="assistant", content=content)
        )

    payload = [{"role": m.role, "content": m.content} for m in req.messages]
    content = assistant.chat(payload)

    return AssistantChatResponse(
        message=AssistantMessage(role="assistant", content=content)
    )


@app.get("/datasets")
def list_datasets() -> list[dict]:
    return datasets.list()


@app.post("/datasets")
def create_dataset(payload: dict) -> dict:
    base = {
        "name": payload.get("name", "dataset"),
        "description": payload.get("description", ""),
        "source_type": payload.get("source_type", "upload"),
        "source_config": payload.get("source_config", {}),
        "labels": payload.get("labels", []),
    }
    return datasets.create(base)


@app.get("/experiments")
def list_experiments() -> list[dict]:
    return experiments.list()


@app.post("/experiments")
def create_experiment(payload: dict) -> dict:
    base = {
        "name": payload.get("name", "experiment"),
        "dataset_id": payload.get("dataset_id"),
        "framework": payload.get("framework", "sklearn"),
        "task_type": payload.get("task_type", "classification"),
        "params": payload.get("params", {}),
        "metrics": payload.get("metrics", {}),
        "status": payload.get("status", "created"),
    }
    return experiments.create(base)


@app.put("/experiments/{experiment_id}")
def update_experiment(experiment_id: str, payload: dict) -> dict:
    try:
        item = experiments.get(experiment_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Experiment not found")
    merged = {**item, **payload, "id": experiment_id}
    return experiments.put(merged)


@app.get("/training/jobs")
def list_training_jobs() -> list[dict]:
    return training_jobs.list()


@app.post("/training/jobs")
def create_training_job(payload: dict) -> dict:
    base = {
        "name": payload.get("name", "training-job"),
        "kind": payload.get("kind", "llm-finetune"),
        "dataset_id": payload.get("dataset_id"),
        "experiment_id": payload.get("experiment_id"),
        "provider": payload.get("provider", "openai"),
        "config": payload.get("config", {}),
        "status": payload.get("status", "queued"),
        "logs": payload.get("logs", []),
    }
    return training_jobs.create(base)


@app.put("/training/jobs/{job_id}")
def update_training_job(job_id: str, payload: dict) -> dict:
    try:
        item = training_jobs.get(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Training job not found")
    merged = {**item, **payload, "id": job_id}
    return training_jobs.put(merged)


@app.post("/ids/new")
def new_id() -> dict[str, str]:
    return {"id": uuid.uuid4().hex}

