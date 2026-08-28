from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class SessionRow(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    generation: Mapped[int] = mapped_column(Integer, default=1)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    content_version: Mapped[str] = mapped_column(String(64), default="vs-0.1.0")
    prep_json: Mapped[dict] = mapped_column(JSON, default=dict)
    battle_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    battle_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    command_receipts: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DomainEventRow(Base):
    __tablename__ = "domain_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    battle_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    envelope_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRunRow(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    battle_id: Mapped[str] = mapped_column(String(64), index=True)
    activation_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    round: Mapped[int] = mapped_column(Integer, default=0)
    side: Mapped[str] = mapped_column(String(32), default="")
    definition_id: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    selected_option_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_subroutine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    offered_option_count: Mapped[int] = mapped_column(Integer, default=0)
    issued_state_version: Mapped[int] = mapped_column(Integer, default=0)
    committed_state_version: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    artifact_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMArtifactRow(Base):
    __tablename__ = "llm_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    battle_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(64), default="tactical")  # tactical|radio
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    response_hash: Mapped[str] = mapped_column(String(64), default="")
    token_usage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Redacted/summary only unless diagnostic mode enables more
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequestLogRow(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(256), index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    battle_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    operation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_host: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxRow(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    battle_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)  # pending|published|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeedbackRow(Base):
    __tablename__ = "feedback_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
