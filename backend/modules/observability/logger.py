"""
Structured JSON logger — append-only, one object per line (.jsonl).

Usage:
    from modules.observability.logger import StructuredLogger

    logger = StructuredLogger()
    logger.log("sess_abc123", "pipeline_start", {"city": "mumbai"})

Logs are written to  logs/<session_id>.jsonl  relative to the backend/ root.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

# logs/ directory lives alongside backend/main.py
_LOGS_DIR: Path = Path(__file__).resolve().parents[2] / "logs"


class StructuredLogger:
    """Thread-safe, append-only JSONL logger."""

    def __init__(self, logs_dir: Path | str | None = None) -> None:
        self._logs_dir = Path(logs_dir) if logs_dir else _LOGS_DIR
        self._lock = threading.Lock()
        self._handles: dict[str, object] = {}  # session_id -> file handle

    # ── public API ────────────────────────────────────────────────────────

    def log(self, session_id: str, event_type: str, payload: dict) -> None:
        """Append one structured JSON record to ``<session_id>.jsonl``."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
        }
        line = json.dumps(record, default=str, ensure_ascii=False) + "\n"

        with self._lock:
            fh = self._handles.get(session_id)
            if fh is None:
                fh = self._open(session_id)
            fh.write(line)  # type: ignore[union-attr]
            fh.flush()  # type: ignore[union-attr]

    def close(self, session_id: str | None = None) -> None:
        """Close one or all open file handles."""
        with self._lock:
            if session_id:
                fh = self._handles.pop(session_id, None)
                if fh:
                    fh.close()  # type: ignore[union-attr]
            else:
                for fh in self._handles.values():
                    fh.close()  # type: ignore[union-attr]
                self._handles.clear()

    # ── internals ─────────────────────────────────────────────────────────

    def _open(self, session_id: str):  # noqa: ANN202
        os.makedirs(self._logs_dir, exist_ok=True)
        path = self._logs_dir / f"{session_id}.jsonl"
        fh = open(path, "a", encoding="utf-8")  # noqa: SIM115
        self._handles[session_id] = fh
        return fh
