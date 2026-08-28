"""ASGI middleware: trace IDs + durable request_logs rows."""

from __future__ import annotations

import re
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..db import SessionLocal
from ..persistence.models import RequestLogRow
from .logging import Timer, clear_trace_context, new_trace_id, set_trace_context, structured_log

SESSION_RE = re.compile(r"/api/v1/sessions/([^/]+)")
BATTLE_RE = re.compile(r"/api/v1/battles/([^/]+)")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        timer = Timer()
        incoming = request.headers.get("x-trace-id") or request.headers.get("x-request-id")
        trace_id = incoming or new_trace_id()

        path = request.url.path
        session_id = None
        battle_id = None
        m = SESSION_RE.search(path)
        if m:
            session_id = m.group(1)
        m = BATTLE_RE.search(path)
        if m:
            battle_id = m.group(1)

        set_trace_context(trace_id=trace_id, session_id=session_id, battle_id=battle_id)
        request.state.trace_id = trace_id

        error_code = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Trace-Id"] = trace_id
            return response
        except Exception as exc:
            error_code = type(exc).__name__
            structured_log(
                "request_failed",
                method=request.method,
                path=path,
                error=str(exc)[:300],
                error_code=error_code,
                duration_ms=timer.ms(),
            )
            raise
        finally:
            duration = timer.ms()
            operation = path.rsplit("/", 1)[-1] if path.startswith("/api/") else path
            try:
                db = SessionLocal()
                db.add(
                    RequestLogRow(
                        trace_id=trace_id,
                        method=request.method,
                        path=path[:256],
                        status_code=status_code,
                        duration_ms=duration,
                        session_id=session_id,
                        battle_id=battle_id,
                        operation=operation[:64],
                        error_code=error_code,
                        client_host=request.client.host if request.client else None,
                        meta_json={"query": str(request.url.query)[:200]},
                    )
                )
                db.commit()
            except Exception as persist_exc:
                structured_log("request_log_persist_failed", error=str(persist_exc)[:200])
            finally:
                try:
                    db.close()
                except Exception:
                    pass
            structured_log(
                "request",
                method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=duration,
                operation=operation,
                error_code=error_code,
            )
            clear_trace_context()
