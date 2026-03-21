from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class KernelStartRequest(BaseModel):
    language: Literal["python", "r"]


class KernelStartResponse(BaseModel):
    kernel_id: str
    language: Literal["python", "r"]


class KernelExecuteRequest(BaseModel):
    kernel_id: str | None = None
    language: Literal["python", "r"] | None = None
    code: str = Field(min_length=0, max_length=5_000_000)
    timeout_s: float = Field(default=30.0, ge=0.1, le=600.0)


class KernelExecuteResponse(BaseModel):
    status: str
    stdout: str
    stderr: str
    result: Any | None = None
    display: list[dict[str, Any]] = Field(default_factory=list)


class SqlQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200_000)


class SqlQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class DbConnectRequest(BaseModel):
    kind: Literal["postgres", "mysql", "snowflake"]
    url: str = Field(min_length=1, max_length=10_000)


class DbConnectResponse(BaseModel):
    id: str
    kind: Literal["postgres", "mysql", "snowflake"]
    url: str


class DbSchemaResponse(BaseModel):
    schemas: list[str] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)


class DbQueryRequest(BaseModel):
    connection_id: str
    query: str = Field(min_length=1, max_length=200_000)
    limit: int = Field(default=5000, ge=1, le=50_000)


class AssistantMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=0, max_length=200_000)


class AssistantChatRequest(BaseModel):
    messages: list[AssistantMessage] = Field(default_factory=list)


class AssistantChatResponse(BaseModel):
    message: AssistantMessage


class NotebookCell(BaseModel):
    id: str
    language: Literal["python", "r", "sql", "markdown"]
    content: str = Field(default="", max_length=5_000_000)


class Notebook(BaseModel):
    id: str
    title: str = Field(default="Untitled notebook", max_length=200)
    cells: list[NotebookCell] = Field(default_factory=list)


class NotebookCreateRequest(BaseModel):
    title: str = Field(default="Untitled notebook", max_length=200)


class NotebookUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    cells: list[NotebookCell] | None = None

