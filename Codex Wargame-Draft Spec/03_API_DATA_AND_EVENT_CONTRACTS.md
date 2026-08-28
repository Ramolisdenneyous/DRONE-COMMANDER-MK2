# Missing Specification 3: API, Data, And Event Contracts

This specification defines stable service boundaries. Exact Python class names may follow repository conventions, but public JSON, transaction behavior, and invariants must remain equivalent.

## 1. Contract Principles

1. All new routes are versioned under `/api/v1`.
2. REST submits commands and reads snapshots; server-sent events deliver ordered server-to-client updates.
3. Every mutation supplies `expected_state_version` and an idempotency key.
4. The backend returns mechanical facts, never only narration.
5. Public DTOs are separate from persistence models.
6. OpenAPI is the source for generated TypeScript API types. Do not hand-maintain duplicate shapes.
7. Internal agent/provider calls are application services, not trusted public mutation routes.

## 2. Session And Battle Lifecycle

### 2.1 Session Status

```text
DRAFT -> ACTIVE -> ENDED
  |         |
  +-> reset +-> reset
```

Reset creates a new empty draft generation under the same session identity or returns a new session ID, according to existing repository behavior. It must never silently overwrite audit events.

### 2.2 Battle Status

```text
INITIALIZING -> ACTIVE -> VICTORY | DEFEAT | DRAW | ABORTED
                    \-> ERROR_RECOVERABLE
```

`ERROR_RECOVERABLE` pauses commands, preserves state, and exposes retry or abort. It is for internal failures that cannot safely use deterministic fallback, not ordinary model/TTS outages.

### 2.3 Preparation Lock

Once deployment succeeds, preparation is immutable for that battle. Changes require reset/rematch and a new battle ID. Lock/deploy is idempotent.

## 3. Public API Surface

### 3.1 System And Catalog

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Process, database, content-version, and migration health |
| GET | `/api/v1/catalog/boot` | Lightweight modes, point caps, commanders, unit summaries, settings defaults |
| GET | `/api/v1/catalog` | Full validated public content catalog |
| GET | `/api/v1/catalog/units/{unit_id}` | One unit definition and resolved references |
| GET | `/api/v1/missions/{mission_id}` | Public mission setup and constraints |

Catalog responses include `content_version`, `schema_version`, ETag, and asset-manifest version.

### 3.2 Sessions And Preparation

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/v1/sessions` | Create a draft session |
| GET | `/api/v1/sessions/{session_id}` | Hydrate authoritative session snapshot |
| PUT | `/api/v1/sessions/{session_id}/prep` | Replace validated draft preparation |
| POST | `/api/v1/sessions/{session_id}/deploy` | Lock prep and create the battle idempotently |
| POST | `/api/v1/sessions/{session_id}/reset` | End/reset current generation and return a draft |
| POST | `/api/v1/sessions/{session_id}/feedback` | Save debrief feedback with consented context |

Preparation includes avatar, loadout, selected RAM abilities, mode, mission/point cap, selected unit definition IDs and counts, optional map preference, and client content version.

### 3.3 Battle Reads And Event Delivery

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/battles/{battle_id}` | Full current battle snapshot |
| GET | `/api/v1/battles/{battle_id}/events` | Paginated event history after sequence number |
| GET | `/api/v1/battles/{battle_id}/stream` | Replayable server-sent event stream |
| GET | `/api/v1/battles/{battle_id}/communications` | Player-readable radio/system projection |
| GET | `/api/v1/battles/{battle_id}/debrief` | Terminal metrics and progression result |

The SSE stream sends heartbeat comments, event IDs, state version, domain events, communication entries, provider state, and animation batches. Clients reconnect with `Last-Event-ID` and hydrate a snapshot if retention no longer covers the gap.

### 3.4 Player Commands

| Method | Route | Purpose |
|---|---|---|
| PUT | `/api/v1/battles/{battle_id}/directives` | Replace global and unit-specific directives during commander activation |
| POST | `/api/v1/battles/{battle_id}/commander/actions` | Execute one offered direct commander action |
| POST | `/api/v1/battles/{battle_id}/commander/end-activation` | Commit directives and end commander activation |
| POST | `/api/v1/battles/{battle_id}/confirmations/{confirmation_id}` | Confirm or reject risky action such as friendly-fire AOE |
| POST | `/api/v1/battles/{battle_id}/abort` | End battle as aborted after confirmation |

The frontend submits an `action_option_id` previously issued by the backend. It does not submit arbitrary destination coordinates, targets, damage, rolls, or RAM totals.

### 3.5 Audio

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/audio/{audio_id}` | Stream or download generated/cached approved audio |
| POST | `/api/v1/battles/{battle_id}/communications/{entry_id}/tts` | Retry TTS for a text entry; never changes battle state |

The normal radio pipeline requests TTS server-side after a communication event. TTS failure returns text-only state and does not fail the activation.

## 4. Command Envelope

Every mutation accepts headers or fields equivalent to:

```json
{
  "command_id": "uuid",
  "expected_state_version": 42,
  "client_content_version": "2026.07.20.1",
  "payload": {}
}
```

`command_id` is the idempotency key. Repeating an already completed command returns the original status/result. Reusing it with a different payload returns `409 IDEMPOTENCY_KEY_REUSED`.

If state version is stale, return `409 STATE_VERSION_CONFLICT` plus the current version and a snapshot URL. Never partially apply the command.

## 5. Snapshot Contract

### 5.1 Session Snapshot

```text
session_id
session_status
generation
state_version
content_version
created_at, updated_at
prep
battle_summary | null
allowed_commands[]
```

### 5.2 Battle Snapshot

```text
battle_id, session_id, status, result
state_version, content_version, seed
mode, mission, point_cap
round, active_activation_id, active_actor_id
initiative[]
map { dimensions, terrain, objectives, visible_effects }
commander { unit view, RAM, signal geometry, remaining actions }
friendly_units[]
opposition_units[]
directives
legal_player_options[]
pending_confirmation | null
communications_cursor
last_event_sequence
```

The public snapshot includes only information the current game mode permits the player to know. MVP may expose all deployed units because full fog of war is deferred, but hidden mines, decoys, and stealth use filtered public views.

### 5.3 Unit View

```text
unit_instance_id, definition_id, display_name, side
category, roles, model_count_alive, model_count_max
hp_current, hp_max, model_hp[] when public
position or formation positions
effective_stats
weapons with public ammo
abilities with public charges/cooldowns
statuses
signal_state
activation_state
asset_set_id
```

## 6. Action Option Contract

The same option structure serves direct commander controls and agent menus. It describes a backend-known plan, not a request for the client/model to calculate mechanics.

```json
{
  "option_id": "activation-id:opaque-token",
  "activation_id": "uuid",
  "actor_id": "commander:player",
  "subroutine": "move_to_cover",
  "label": "Move behind the central barrier",
  "action_cost": {"move": 1},
  "target_refs": ["hex:17:22"],
  "preview": {
    "path": [[16, 25], [17, 24], [17, 23], [17, 22]],
    "movement_cost": 4,
    "affected_hexes": [],
    "risk_tags": ["light_cover", "exposed_from_east"]
  },
  "issued_state_version": 42,
  "expires_with_activation": true
}
```

Option IDs are opaque and scoped to one activation/state version. The backend stores or can reproduce their resolved plans. It rejects invented, expired, wrong-actor, or modified options.

## 7. Event Contract

### 7.1 Event Envelope

```json
{
  "event_id": "uuid",
  "session_id": "uuid",
  "battle_id": "uuid",
  "sequence": 381,
  "state_version": 43,
  "batch_id": "uuid",
  "type": "attack_resolved",
  "schema_version": 1,
  "occurred_at": "RFC-3339 timestamp",
  "actor_id": "friendly:2",
  "causation_id": "command-or-activation-id",
  "correlation_id": "request-or-activation-id",
  "visibility": "public",
  "payload": {}
}
```

Sequences are unique and increasing within a session. Events in one resolution share `batch_id`; the projection version advances once per committed batch.

### 7.2 Minimum Event Types

Lifecycle:

- `session_created`
- `prep_updated`
- `battle_deployed`
- `battle_started`
- `battle_completed`
- `battle_aborted`
- `session_reset`

Round and activation:

- `round_started`
- `initiative_rolled`
- `activation_started`
- `action_spent`
- `activation_completed`
- `activation_skipped`

Battle mechanics:

- `unit_moved`
- `weapon_fired`
- `attack_resolved`
- `damage_applied`
- `resource_changed`
- `status_applied`
- `status_expired`
- `model_destroyed`
- `unit_defeated`
- `terrain_changed`
- `mine_revealed`
- `transport_loaded`
- `transport_unloaded`
- `objective_updated`

Command and agents:

- `directive_updated`
- `agent_choice_requested`
- `agent_choice_received`
- `agent_choice_stale`
- `agent_fallback_used`
- `communication_added`
- `tts_requested`
- `tts_ready`
- `tts_failed`

Animation cues are a derived delivery projection and should reference domain event IDs. They are not mechanical source-of-truth events.

## 8. Transaction And Projection Model

For every state-changing command:

1. Begin transaction and lock the session/battle projection row.
2. Check idempotency receipt and expected version.
3. Load authoritative projection and content version.
4. Validate command and resolve deterministic rules.
5. Append ordered events.
6. Update normalized projections and snapshot data.
7. Increment state version once.
8. Store command receipt with result reference.
9. Commit.
10. Publish SSE/worker notifications from an outbox after commit.

Use a transactional outbox so a database commit cannot be lost merely because a process crashes before publishing. Consumers are idempotent by event ID.

The event log must contain enough mechanical facts to audit and rebuild battle state when combined with the locked content version and initial seed. Periodic snapshots may accelerate recovery.

## 9. Persistence Model

Recommended tables:

| Table | Purpose |
|---|---|
| `sessions` | Lifecycle, generation, version, content version, timestamps |
| `session_prep` | Draft/locked avatar, loadout, abilities, mode, cap, army |
| `battles` | Status, result, seed, round, active activation, current projection |
| `unit_instances` | Queryable current unit/model/resource/status projection |
| `domain_events` | Append-only ordered events |
| `command_receipts` | Idempotency key, request hash, result reference |
| `outbox` | Durable post-commit deliveries |
| `agent_runs` | Activation/provider status, hashes, timings, selected option, failure/fallback |
| `llm_artifacts` | Redacted or externalized prompt/output references for debugging |
| `memory_blocks` | Stable battle lock and round summaries |
| `generated_audio` | Text hash, provider metadata, storage path, duration, status |
| `feedback_submissions` | User feedback and explicitly included session context |

Indexes must support session event sequence, battle unit lookup, active agent run, command ID, and outbox delivery status.

## 10. Agent Run State

```text
CREATED -> REQUESTED -> PROVISIONAL -> VALIDATED -> COMMITTED
                  |          |             |
                  +-> FAILED +-> STALE     +-> FALLBACK
```

An agent run records `activation_id`, actor, prompt template versions, context hash, offered option IDs, provider/model name, request attempt, timestamps, token/cost metadata where available, selected option, validation result, fallback, and final communication reference.

Raw secrets are never stored. Full prompt/output retention is configurable and off by default in production; hashes and bounded redacted previews remain available.

## 11. Error Contract

```json
{
  "error": {
    "code": "STATE_VERSION_CONFLICT",
    "message": "The battle changed before this action was applied.",
    "details": {},
    "current_state_version": 43,
    "trace_id": "uuid",
    "recoverable": true
  }
}
```

Canonical status behavior:

- `400`: malformed semantics not covered by schema.
- `401/403`: authentication or authorization when enabled.
- `404`: unknown public resource.
- `409`: lifecycle, stale version, idempotency, or already-terminal conflict.
- `422`: schema/content validation failure with field paths.
- `429`: rate limit; combat uses fallback rather than waiting indefinitely.
- `503`: unavailable dependency for operations that truly require it.

Player-facing messages use plain language. Internal detail remains in structured logs keyed by `trace_id`.

## 12. Legacy Migration Boundary

The source copied these concepts from Story Engine: `tab1_inputs`, party/player IDs, monsters, adventures, travel, narrative builders, Moosehearth returns, celebration songs, and `story_engine_cyberpunk` database naming.

Migration rules:

1. Inspect real schema and usage before changing or deleting anything.
2. Add Drone Commander tables/routes alongside legacy paths if a compatibility period is needed.
3. Migrate data with explicit versioned migrations.
4. Route adapters may translate legacy calls temporarily but new frontend code uses only `/api/v1` contracts.
5. Remove legacy paths only after tests prove no active caller depends on them and Raymond approves destructive cleanup.

## 13. API Acceptance

- OpenAPI validates and generates the client without manual corrections.
- Deploy, action, end-activation, reset, and feedback are idempotent.
- Concurrent commands against one version yield one commit and one conflict, never two commits.
- Refresh and SSE replay reproduce the same visible state.
- Hidden information is absent from public DTOs.
- Every error supplies a stable machine code and trace ID.
- A database commit followed by process termination is eventually delivered through the outbox.
- Legacy route names do not appear in new frontend code.

