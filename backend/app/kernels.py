from __future__ import annotations

import queue
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from jupyter_client import KernelManager


KernelLanguage = Literal["python", "r"]


@dataclass
class KernelSession:
    id: str
    language: KernelLanguage
    km: KernelManager


class KernelService:
    """
    Minimal in-memory Jupyter kernel manager.
    - Python kernel works out of the box (ipykernel installed).
    - R kernel requires IRkernel installed in the user's R environment.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, KernelSession] = {}

    def start(self, language: KernelLanguage) -> KernelSession:
        kernel_name = "python3" if language == "python" else "ir"
        km = KernelManager(kernel_name=kernel_name)

        try:
            km.start_kernel()
        except Exception as e:
            raise RuntimeError(
                f"Failed to start {language} kernel ({kernel_name}). "
                f"For R: install IRkernel in R, then register it. Details: {e}"
            )

        session_id = uuid.uuid4().hex
        sess = KernelSession(id=session_id, language=language, km=km)
        self._sessions[session_id] = sess
        return sess

    def stop(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if not sess:
            return
        try:
            sess.km.shutdown_kernel(now=True)
        except Exception:
            pass

    def execute(self, session_id: str, code: str, timeout_s: float = 30.0) -> dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            raise KeyError("Kernel session not found")

        kc = sess.km.client()
        kc.start_channels()

        msg_id = kc.execute(code)
        started = time.time()

        stdout: list[str] = []
        stderr: list[str] = []
        result: Any = None
        display: list[dict[str, Any]] = []
        status: str | None = None

        def timed_out() -> bool:
            return (time.time() - started) > timeout_s

        # Drain messages until idle for this execution.
        while True:
            if timed_out():
                status = status or "timeout"
                break

            try:
                msg = kc.get_iopub_msg(timeout=0.2)
            except queue.Empty:
                continue

            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue

            msg_type = msg.get("header", {}).get("msg_type")
            content = msg.get("content", {}) or {}

            if msg_type == "stream":
                name = content.get("name")
                text = content.get("text", "")
                if name == "stderr":
                    stderr.append(text)
                else:
                    stdout.append(text)
            elif msg_type in ("execute_result", "display_data"):
                data = content.get("data", {}) or {}
                display.append(data)
                if msg_type == "execute_result":
                    # Prefer text/plain if present
                    if "text/plain" in data:
                        result = data["text/plain"]
                    else:
                        result = data
            elif msg_type == "error":
                tb = content.get("traceback") or []
                stderr.append("\n".join(tb) if tb else (content.get("evalue") or "Error"))
            elif msg_type == "status":
                status = content.get("execution_state")
                if status == "idle":
                    break

        try:
            kc.stop_channels()
        except Exception:
            pass

        return {
            "status": status or "unknown",
            "stdout": "".join(stdout),
            "stderr": "".join(stderr),
            "result": result,
            "display": display,
        }

