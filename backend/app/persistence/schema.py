"""Lightweight schema ensure for iterative VS development (no Alembic yet)."""

from __future__ import annotations

from sqlalchemy import text

from ..db import engine
from ..telemetry.logging import structured_log


def ensure_schema() -> None:
    """Create missing tables/columns for observability without wiping data when possible."""
    statements = [
        # sessions extras
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_trace_id VARCHAR(64)",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS notes_json JSONB DEFAULT '{}'::jsonb",
        # domain_events extras
        "ALTER TABLE domain_events ADD COLUMN IF NOT EXISTS event_type VARCHAR(64) DEFAULT ''",
        "ALTER TABLE domain_events ADD COLUMN IF NOT EXISTS state_version INTEGER DEFAULT 0",
        "ALTER TABLE domain_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        # agent_runs extras (table may be new via create_all)
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS session_id VARCHAR(64) DEFAULT ''",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS round INTEGER DEFAULT 0",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS side VARCHAR(32) DEFAULT ''",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS definition_id VARCHAR(128) DEFAULT ''",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS selected_subroutine VARCHAR(64)",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS fallback_reason TEXT",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS offered_option_count INTEGER DEFAULT 0",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS issued_state_version INTEGER DEFAULT 0",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS committed_state_version INTEGER DEFAULT 0",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS duration_ms DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64)",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        # feedback
        "ALTER TABLE feedback_submissions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    ]
    with engine.begin() as conn:
        for sql in statements:
            try:
                conn.execute(text(sql))
            except Exception as exc:
                # Table may not exist yet; create_all runs first.
                structured_log("schema_alter_skip", sql=sql[:80], error=str(exc)[:160])
    structured_log("schema_ensure_complete")
