"""Structured logging and request/activation tracing helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..config import settings

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
battle_id_var: ContextVar[str | None] = ContextVar("battle_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or trace_id_var.get(),
            "session_id": getattr(record, "session_id", None) or session_id_var.get(),
            "battle_id": getattr(record, "battle_id", None) or battle_id_var.get(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def setup_logging() -> logging.Logger:
    level_name = getattr(settings, "log_level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger = logging.getLogger("drone_commander")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    # Quiet noisy libs a bit
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    return logger


log = setup_logging()


def new_trace_id() -> str:
    return uuid4().hex


def set_trace_context(
    *,
    trace_id: str | None = None,
    session_id: str | None = None,
    battle_id: str | None = None,
) -> str:
    tid = trace_id or trace_id_var.get() or new_trace_id()
    trace_id_var.set(tid)
    if session_id is not None:
        session_id_var.set(session_id)
    if battle_id is not None:
        battle_id_var.set(battle_id)
    return tid


def clear_trace_context() -> None:
    trace_id_var.set(None)
    session_id_var.set(None)
    battle_id_var.set(None)


def structured_log(event: str, **fields: Any) -> None:
    """Emit one JSON log line with safe identifiers."""
    # Never log secrets
    scrubbed = {k: v for k, v in fields.items() if k.lower() not in {"authorization", "api_key", "openai_api_key"}}
    record = log.makeRecord(
        log.name,
        logging.INFO,
        "(telemetry)",
        0,
        event,
        args=(),
        exc_info=None,
    )
    record.extra_fields = {"event": event, **scrubbed}
    record.trace_id = scrubbed.get("trace_id") or trace_id_var.get()
    record.session_id = scrubbed.get("session_id") or session_id_var.get()
    record.battle_id = scrubbed.get("battle_id") or battle_id_var.get()
    log.handle(record)


def hash_payload(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def redact_text(text: str, keep: int = 48) -> str:
    if not text:
        return ""
    if getattr(settings, "artifact_retention_mode", "metadata") == "full_diagnostic":
        return text[:2000]
    if len(text) <= keep:
        return text
    return text[:keep] + "…"


class Timer:
    def __init__(self) -> None:
        self.start = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self.start) * 1000.0, 2)
