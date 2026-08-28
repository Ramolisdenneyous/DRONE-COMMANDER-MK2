from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class DomainEvent:
    type: str
    payload: dict[str, Any]
    actor_id: str | None = None
    visibility: str = "public"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    batch_id: str | None = None
    causation_id: str | None = None
    correlation_id: str | None = None

    def to_envelope(
        self,
        *,
        session_id: str,
        battle_id: str | None,
        sequence: int,
        state_version: int,
        schema_version: str = "1",
    ) -> dict[str, Any]:
        from datetime import datetime, timezone

        return {
            "event_id": self.event_id,
            "session_id": session_id,
            "battle_id": battle_id,
            "sequence": sequence,
            "state_version": state_version,
            "batch_id": self.batch_id,
            "type": self.type,
            "schema_version": schema_version,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "actor_id": self.actor_id,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "visibility": self.visibility,
            "payload": self.payload,
        }
