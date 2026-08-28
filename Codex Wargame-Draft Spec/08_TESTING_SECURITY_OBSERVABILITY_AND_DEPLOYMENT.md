# Missing Specification 8: Testing, Security, Observability, And Deployment

This document supplies the release engineering and operational contract absent from the source. A wargame with asynchronous agents is not done when one happy-path battle works once.

## 1. Quality Strategy

Test the deterministic game underneath the models first. Live model and media providers are optional integration layers and must not be required for normal continuous integration.

Test layers:

1. Content/schema validation.
2. Pure rules unit and property tests.
3. Application transaction and persistence tests.
4. API contract tests.
5. Agent orchestration tests with scripted fake providers.
6. Frontend component and state tests.
7. PixiJS scene/animation contract tests.
8. Browser end-to-end acceptance tests.
9. Headless simulation, concurrency, and soak tests.
10. Optional live-provider smoke tests in a protected environment.

## 2. Test Determinism

Every test battle supplies an explicit seed. Fixtures record content version, map ID/generator version, force definitions, and ordered commands.

Failure output must print:

- seed
- content version
- test/scenario ID
- battle/session IDs
- last state version and event sequence
- recent event types
- trace ID

A failed random/property test writes a minimized replay fixture that can run locally without a provider.

## 3. Content Validation Tests

Backend startup and CI reject:

- duplicate or malformed IDs
- missing unit/weapon/ability/terrain/map/mission/prompt/asset references
- illegal negative costs, ranges, HP, or charges
- point caps with no legal force
- unit definitions with no legal fallback behavior
- maps without valid deployment or reachable objectives
- impossible objective graphs
- unsupported schema versions
- missing production-approved required assets for a release build
- prompt templates incompatible with the current decision schema

Snapshots of the public boot catalog detect accidental contract churn.

## 4. Rules Unit And Property Tests

### Unit Examples

- 3d6 hit ties Defense.
- Damage tie against Armor deals zero.
- Damage never spills between models or goes below zero HP.
- Standard downgrades once and never creates two extra actions.
- A two-Move activation cannot split one Move around an attack.
- A* respects terrain, occupancy, flying, and stable tie order.
- LOS edge ambiguity evaluates consistently.
- Cover uses highest source rather than stacking.
- AOE includes exact axial radius and applies friendly fire.
- RAM refreshes and signal uses capacity, not current RAM.
- Destroyed, loaded, or out-of-signal actors receive correct menus.
- Transport destruction places and damages every passenger deterministically.
- Mine trigger interrupts movement in correct event order.
- Commander destruction terminates once.

### Property Invariants

Across generated legal states:

- HP/resources are bounded.
- occupancy is legal.
- movement result is reachable within cost.
- events and versions are monotonic.
- each living eligible actor activates at most once per round.
- terminal battles reject mutation.
- replay from initial state plus events equals current projection.
- same seed and commands equal same events, excluding timestamps/UUIDs normalized for comparison.

## 5. Persistence And API Tests

Use a real PostgreSQL test service for transaction behavior. Test:

- migration from empty database
- migration from representative legacy Story Engine schema/data
- deploy and reset idempotency
- command receipt replay and key-reuse conflict
- simultaneous commands against one state version
- row locking and rollback after injected exceptions
- outbox recovery after publish failure
- SSE order, reconnect, Last-Event-ID replay, and retention fallback
- hidden-state filtering
- OpenAPI client generation
- terminal-state conflicts
- snapshot/event replay consistency

Database cleanup is scoped to the test database only.

## 6. Agent Contract Tests

Scripted fake providers return:

- valid offered option
- wrong actor
- invented option
- malformed JSON/tool call
- no tool call
- timeout
- rate limit
- provider exception
- result after unit is defeated
- result after target/path becomes stale
- five responses in reverse initiative order

Assert one legal commit, correct retry budget, deterministic fallback, no duplicate activation, cancellation/ignore behavior, artifact metadata, and radio truthfulness.

Prompt snapshot tests verify trusted block order, hidden-state filtering, bounded size, and current schemas. They should not make minor prose edits painful; compare structural blocks and key prohibitions separately from creative voice fixtures.

## 7. Frontend And PixiJS Tests

Component tests cover prep validation, point/unit counters, loadout/ability selection, disabled reasons, initiative states, directives, communication scroll behavior, audio settings, reconnect banners, and debrief actions.

PixiJS tests cover:

- coordinate projection and hit testing
- named layer order
- depth sorting
- snapshot hydration
- ordered event-batch animation
- cancellation/snap on reconnect
- camera clamping and center controls
- cleanup of ticker/listeners/textures/audio across remount
- reduced-motion timing
- nonblank rendering and expected overlay pixels

Do not assert fragile exact antialiasing pixels across all platforms. Use semantic scene assertions plus tolerant image comparison.

## 8. End-To-End Scenarios

Automate at least:

1. First run, skip tutorial, build/deploy 15-point force.
2. Complete one deterministic battle through commander and fallback-agent turns.
3. Use Move, Attack, one RAM ability, one directive, and End Activation.
4. Friendly-fire AOE confirmation accept and reject paths.
5. Refresh during commander activation and during an agent activation.
6. Disconnect/reconnect SSE without duplicate animation or command.
7. Model disabled and TTS disabled from boot.
8. Provider timeout mid-battle.
9. Victory, defeat, abort, rematch, reset, and feedback.
10. Keyboard-only path from draft through Debrief.
11. Reduced-motion and mute settings.
12. Required desktop, tablet, and phone screenshots with overlap checks.

## 9. Simulation And Performance

### 9.1 Headless Simulation

Run deterministic fallback-vs-fallback battles across each point cap, map family, objective type, and doctrine. Store aggregate balance telemetry but retain individual replays only for failures or sampled diagnostics.

Minimum pre-release suite **TUNING**:

- 100 battles per point cap in ordinary CI/nightly division.
- 1,000 mixed 100-point battles in release soak.
- No deadlock, invariant failure, illegal action, duplicate activation, or unreplayable event history.

### 9.2 Backend Targets

- Ordinary rules command p95 below 250 ms excluding provider/media time **TUNING**.
- Snapshot p95 below 500 ms at 100 points **TUNING**.
- Legal option generation p95 below 500 ms per actor **TUNING**.
- Twenty unit identities and five in-flight provider calls without queue corruption.
- Bounded memory/event payload growth over a long battle.

### 9.3 Frontend Targets

Use the rendering targets in the asset specification. Add browser memory checks across five rematches/tab mounts and assert no monotonic scene/listener growth beyond a small tolerance.

## 10. Continuous Integration Gates

Recommended jobs:

- formatting/lint/type checks
- content validation
- backend unit/property tests
- PostgreSQL integration/API tests
- frontend unit/build tests
- browser smoke tests with captured artifacts
- Docker Compose build and health test
- dependency/license/security scan
- migration upgrade test
- nightly simulation/soak

PR gates use fake providers and local placeholder media. Live-provider tests are manual or scheduled with strict spending and secret controls.

## 11. Security Model

### 11.1 Trust Boundaries

- Browser input is untrusted.
- Model output is untrusted.
- generated/content-pack text is untrusted until validated and approved.
- Backend domain logic is the only mechanical authority.
- Provider API keys and database credentials exist only server-side.

### 11.2 Session Access

For a public anonymous deployment, possession of a session UUID is not sufficient authorization. Issue an unguessable signed session-access token in a Secure, HttpOnly, SameSite cookie and protect mutations with same-origin policy plus CSRF token/header as appropriate.

If the first deployment is strictly local/single-user, the code may run in local-trust mode, but production mode must not inherit that assumption.

### 11.3 Required Controls

- Strict request schemas, size limits, and enum validation.
- CORS allowlist; no wildcard credentials.
- Rate limits by session and network identity for session creation, commands, model calls, TTS, and feedback.
- HTML escaping/safe rendering for directives, names, model output, and errors.
- No arbitrary URL fetch, file path, shell command, or executable mission script from content.
- Secrets loaded through environment/provider secret store and redacted from logs/artifacts.
- Dependency pinning and automated vulnerability review.
- Content Security Policy appropriate to app/media origins.
- Authorization filtering before snapshots/events are returned.
- Administrative/debug endpoints disabled or protected in production.

## 12. Privacy And Retention

Before a player sends natural-language directives to an external model or TTS provider, the application explains that text may be processed by the configured service. Provider choices and retention follow their current agreements and deployment configuration.

Production defaults:

- Store mechanical events and bounded communications needed for the session.
- Store prompt/output hashes and metadata; full raw artifacts are off unless diagnostic consent/config enables them.
- Never store provider secrets.
- Feedback states exactly what context is attached and allows omission.
- Provide session deletion or documented expiration for publicly hosted anonymous sessions.
- Make retention windows configuration values and include a cleanup job.

Do not send hidden server metadata, credentials, unrelated event history, or player identifiers to model/TTS providers.

## 13. Observability

### 13.1 Structured Logs

Every request/activation log includes safe identifiers:

- trace/correlation ID
- session and battle ID
- state version and event sequence where relevant
- actor and activation ID
- operation and duration
- outcome/error code
- provider attempt and fallback flag

Avoid raw prompt, directive, TTS text, and secret values in normal production logs.

### 13.2 Metrics

Track:

- request latency/error by route
- active sessions/battles
- command conflicts and idempotent replays
- option generation and rules resolution latency
- provider decision/radio/TTS latency, retry, timeout, fallback, tokens, and estimated cost
- queue depth, in-flight calls, and stale-choice rate
- SSE connections/reconnects and outbox lag
- battle duration, rounds, result, point cap, and invariant failures
- content validation and asset load failures

### 13.3 Tracing

Trace a command from HTTP through transaction, events, outbox, SSE, and animation-batch acknowledgement where available. Trace agent activation across context build, provider, revalidation, resolution, radio, and TTS with sensitive payloads excluded.

### 13.4 Alerts

Alert on sustained backend errors, database/migration failure, outbox lag, high fallback/timeout rate, runaway provider spending, content startup failure, and repeated invariant violations. A single provider outage should degrade to fallback and alert without making the app unavailable.

## 14. Cost Controls

Configuration supports:

- maximum decision calls per battle
- maximum in-flight calls
- input/output token ceilings
- per-session and global daily spending limits
- snapshot image on/off
- radio generation on/off or template-only
- TTS on/off and cache limits
- provider/model selection by task

When limits are reached, degrade in this order: disable prefetch, omit images, use templated radio, disable generated TTS, use deterministic tactical fallback. Never leave a unit waiting indefinitely.

## 15. Configuration

Representative environment variables:

```text
APP_ENV
DATABASE_URL
PUBLIC_APP_ORIGIN
CONTENT_PATH
ASSET_PATH
CONTENT_VERSION_OVERRIDE
SESSION_SIGNING_SECRET
CSRF_SECRET
MODEL_PROVIDER
MODEL_API_KEY
TACTICAL_MODEL
RADIO_MODEL
MAX_AGENT_CONCURRENCY
AGENT_DECISION_TIMEOUT_SECONDS
AGENT_RETRY_TIMEOUT_SECONDS
TTS_PROVIDER
TTS_API_KEY
ARTIFACT_RETENTION_MODE
LOG_LEVEL
OTEL_EXPORTER_OTLP_ENDPOINT
```

Startup checks required production values and refuses insecure defaults. `.env.example` contains names and safe examples only.

## 16. Docker Development

Canonical local endpoints:

- PostgreSQL host port 5436.
- Backend `http://localhost:8004`, internal 8000.
- Frontend `http://localhost:5177`, internal Vite 5173.

`docker compose up --build` must start a usable stack from a clean checkout after documented environment setup. Health checks wait for database readiness, migrations, and content validation. Frontend health verifies served application; backend health distinguishes liveness and readiness.

Development commands and test entry points belong in the repository README/Makefile/task runner and CI, not only this spec.

## 17. Railway/Production Deployment

Before production deployment:

- Use managed PostgreSQL and a durable asset/audio store; do not rely on container-local generated files.
- Run migrations as a one-off release step with backup and rollback plan.
- Serve frontend and immutable hashed assets through suitable static hosting/CDN or the chosen service architecture.
- Configure public origin, TLS, health routes, CORS/CSP, secrets, resource limits, and retention jobs.
- Scale backend with shared database/outbox/queue semantics; process memory is not authoritative battle state.
- Ensure SSE proxy timeouts/keepalive and reconnect behavior are tested on the real platform.
- Pin content/asset versions per release.

The implementing agent must verify current Railway behavior and repository deployment conventions at implementation time rather than trusting copied Story Engine settings.

## 18. Migrations, Backups, And Rollback

- Every schema change is a reviewed migration.
- CI upgrades from empty and representative prior versions.
- Production migration has backup/restore instructions and a compatibility window when rollback would otherwise break the old app.
- Content schema changes include converter or explicit incompatibility decision.
- Release rollback never points old code at irreversibly migrated data without validation.
- Destructive legacy cleanup is a separate approved change after Drone Commander behavior is stable.

## 19. Release Checklist

- All CI and release soak tests pass.
- No open critical/high security issue.
- Content and asset manifests validate and are versioned.
- Required media has approval/license metadata.
- Provider-disabled battle works.
- Production secrets, origins, rate limits, retention, and cost caps are set.
- Migration backup and rollback are rehearsed.
- Required viewport/accessibility checks pass.
- Error, reconnect, provider outage, and database restart drills pass.
- Product owner approves gameplay tuning and final assets separately from technical completion.

