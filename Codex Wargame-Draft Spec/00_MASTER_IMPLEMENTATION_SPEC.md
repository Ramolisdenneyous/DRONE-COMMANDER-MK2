# Drone Commander: Master Implementation Specification

Version: 0.9 draft  
Product owner: Raymond  
Primary implementation target: Web application  
Primary mode: Single-player tactical wargame against AI-controlled opposition

## 1. Product Definition

Drone Commander is a turn-based tactical wargame in which the player directly controls a vulnerable battlefield commander and gives intent-level orders to AI-controlled squads and drones. The game is played on a backend-authoritative hex battlefield presented as a fixed-camera 2.5D tactical command display.

The core fantasy is not manually driving every piece. The player positions the commander, spends RAM on force-multiplying abilities, issues tactical intent, and watches semi-autonomous units execute within the legal choices calculated by the rules engine.

The product pillars are:

1. **Command, not micromanagement.** One agent controls one battlefield unit; a soldier squad is one unit even when several models are shown.
2. **Server-resolved reality.** Dice, legality, paths, line of sight, damage, resources, objectives, and victory are decided by deterministic backend code.
3. **Readable combined-arms tactics.** Terrain, cover, signal range, weapon range, initiative, and objectives are visible without requiring rules archaeology.
4. **Bounded expressive agents.** Language models select from legal tactical options and provide brief radio reports; they do not simulate the rules.
5. **Content that can be tuned.** Units, weapons, abilities, terrain, missions, prompts, and asset manifests live in validated, human-readable content files.

## 2. Setting And Tone

The setting is near-modern speculative military fiction. The player serves a fictional multinational security coalition. Opposing factions evoke broad geopolitical and technological pressures without directly reproducing a current real-world army, conflict, insignia, or named political actor.

The presentation combines elite special-operations professionalism with a restrained near-future command system. It should feel tactical, tense, and functional rather than celebratory about real-world harm.

## 3. Delivery Scope

### 3.1 VS: 15-Point Vertical Slice

The vertical slice proves the complete loop with the smallest useful content set:

- One prepared 50 by 50 hex battlefield.
- One commander base chassis, at least two visual avatars, one commander loadout, and three selectable RAM abilities.
- One soldier squad type: Infantry.
- Three drone types: One-Way Attack, Direct Attack, and Support.
- A deterministic equal-cap opposition builder using mirrored mechanical templates and distinct faction presentation.
- Automated deployment.
- Commander-first rounds, initiative, movement, attacks, damage, destruction, one objective type, victory, defeat, and debrief.
- One friendly agent per non-commander unit and one opposition agent per enemy unit.
- Legal tactical option generation, bounded agent selection, deterministic fallback, short friendly radio replies, and a communications log.
- PixiJS battlefield with terrain, selection, movement range, weapon range, signal range, basic movement/attack/damage animations, and initiative cards.
- Docker Compose development environment and automated backend, frontend, and end-to-end smoke tests.

The VS point limit is fixed at 15. Its purpose is architectural validation, not a content-complete release.

### 3.2 MVP: Complete Freestyle Battle

The Freestyle MVP adds:

- Point caps of 15, 25, 40, 55, 75, and 100.
- Three soldier squad types.
- Seven drone catalog entries. The source summary said six but defined seven; seven is canonical.
- Six commander equipment loadouts and all seven commander RAM abilities.
- Up to ten non-commander units per side.
- Prepared and seeded semi-procedural maps.
- Annihilation, control-point, and extraction objective templates.
- Full terrain set, status effects, ordnance, transport, mines, smoke, painting, and resupply.
- Debrief metrics, rematch, reset, settings, audio controls, and feedback submission.
- Reliable handling of up to twenty concurrent unit identities with no more than five model requests in flight.

### 3.3 Campaign Release

The campaign is a later release built on the stable Freestyle rules. It contains six missions with point limits of 15, 25, 40, 55, 75, and 100. It progressively teaches movement, cover, signal range, RAM, painting, support, mines, objectives, and combined-arms command.

### 3.4 Explicit Non-Goals For VS And MVP

- Multiplayer.
- User-generated maps or mod distribution.
- A strategic world map or economy.
- Permanent soldier inventory or permadeath.
- Manual deployment.
- An enemy Drone Commander or enemy RAM economy.
- Full fog of war, sensor simulation, or advanced electronic warfare.
- Free-form LLM control of coordinates, dice, damage, or game state.
- Runtime generation of final production art, music, or sound effects.

## 4. Success Criteria

The Freestyle MVP succeeds when a first-time player can build an army, deploy, understand whose activation is current, issue an order, see legal movement and targets, complete a battle, and understand the result without consulting the source document.

Operationally, a complete 100-point automated simulation must finish without illegal state, duplicate activation, stale action commitment, unhandled exception, or agent deadlock. The app must remain playable if all model or TTS providers are unavailable by using deterministic tactical fallbacks and text-only communications.

## 5. Canonical Terminology

| Canonical term | Meaning | Replaces or clarifies |
|---|---|---|
| Defense | Target number for an attack roll | Defiance, defence |
| Armor | Target number for a damage roll | Armer |
| Minor action | Lowest-value action category | Swift action |
| Unit | One activation and one agent identity | Squad, drone, solo, grouped asset as actors |
| Model | An individual soldier or single displayed body within a unit | Party member, monster instance |
| Friendly | The player's side | Player character, party |
| Opposition | The enemy side | Monster, NPC combatant |
| Battle | One tactical match | Encounter, adventure combat |
| Mission | Rules, map, objective, and force constraints for a battle | Adventure, chapter |
| Commander directive | Persistent player intent assigned to units | Prompt, narrative command |
| Tactical option | Backend-generated legal subroutine offered to an agent | Raw tool action |
| Event | Immutable record of a domain fact | Transcript mutation |

All code, schemas, APIs, tests, and player-facing rules text must use canonical terms. Legacy database or route names may remain only behind an explicit migration adapter and must not appear in new public contracts.

## 6. Technical Architecture

### 6.1 Runtime Services

Docker Compose contains three primary services:

| Service | Technology | Host port | Container port | Responsibility |
|---|---|---:|---:|---|
| `postgres` | PostgreSQL | 5436 | 5432 | Durable sessions, projections, events, agent metadata, feedback |
| `backend` | FastAPI | 8004 | 8000 | Authoritative rules, orchestration, persistence, content validation, provider adapters |
| `frontend` | React 18, TypeScript, Vite, PixiJS | 5177 | 5173 | Application shell, player input, battlefield rendering, animation, audio playback |

The canonical development database name is `drone_commander`. The inherited `story_engine_cyberpunk` name is legacy residue and should be migrated, not propagated.

### 6.2 Ownership Boundaries

The backend owns:

- Session and battle lifecycle.
- Versioned content catalogs.
- Army validation and opposition construction.
- Deployment, coordinates, occupancy, terrain, movement, pathfinding, and line of sight.
- Initiative, action economy, dice, attacks, damage, resources, status effects, objectives, destruction, victory, and defeat.
- Tactical option generation and agent activation orchestration.
- Append-only events and current-state projections.
- Provider requests, prompt artifacts, retry policy, and TTS request generation.

The React shell owns:

- Routing or tab state, forms, settings, focus management, and accessible controls.
- API commands and hydration from backend snapshots/events.
- Mission Prep, battle shell, communications, inspector, and Debrief presentation.
- Audio controls and browser playback policy.

PixiJS owns:

- Battlefield scene graph, camera, zoom/pan, hit testing, overlays, particles, and animation playback.
- High-frequency visual state that must not run through React on every frame.

Language-model agents own only:

- Choosing one offered tactical option.
- Choosing an allowed fallback preference.
- Producing a brief radio acknowledgement after backend resolution.

### 6.3 Required Architectural Properties

- **ARCH-001:** Every state-changing command is validated by the backend.
- **ARCH-002:** A committed command and its domain events are stored in one database transaction.
- **ARCH-003:** Every battle state has a monotonic `state_version`.
- **ARCH-004:** Repeated commands with the same idempotency key do not apply twice.
- **ARCH-005:** Content validation runs at backend startup and fails fast with a precise path and reason.
- **ARCH-006:** A supplied seed makes dice, tie breaks, force building, deployment, and map generation reproducible.
- **ARCH-007:** Provider failure cannot block battle progression.
- **ARCH-008:** Game content, prompts, rules code, provider adapters, and UI code are separate ownership areas.

## 7. Proposed Repository Shape

The implementing agent should adapt this shape to the actual repository rather than force a destructive rewrite:

```text
backend/app/
  api/                 # FastAPI routes, request/response models
  domain/              # Entities, value objects, enums, invariants
  engine/              # Initiative, movement, LOS, combat, effects, objectives
  agents/              # Context builder, option builder, queue, provider adapters
  application/         # Use cases and transaction orchestration
  persistence/         # Repositories, SQLAlchemy models, migrations
  content/             # Catalog loader and validation
  telemetry/           # Structured logs, metrics, tracing helpers
content/
  units/ weapons/ abilities/ terrain/ maps/ missions/ factions/ prompts/
frontend/src/
  app/                 # Shell, routes/tabs, global providers
  features/prep/
  features/battle/
  features/debrief/
  pixi/                # Scene, layers, camera, entity views, animation queue
  api/                  # Generated or shared client types and transport
  audio/
tests/
  fixtures/ seeds/ e2e/
```

Avoid a single expanding `services.py`. Existing entry points may delegate into these modules during migration.

## 8. Content Model

Game content must be data-driven and versioned. The minimum catalogs are:

- Unit definitions.
- Weapon definitions.
- Ability definitions.
- Commander loadouts.
- Terrain definitions.
- Faction presentation and agent doctrine.
- Prepared maps and generation templates.
- Objective definitions and missions.
- Prompt templates.
- Asset manifest and audio cue manifest.

Runtime unit instances reference immutable definition IDs plus a `content_version`. Save files must continue to resolve against the content version with which the battle began.

Unit IDs must exactly match references in missions, maps, armies, prompt identities, and assets. Validation must reject duplicate IDs, missing references, illegal costs, unknown action types, invalid ranges, and absent required assets.

## 9. Core Game Loop

### 9.1 Mission Prep

The player:

1. Chooses a commander avatar. Avatars are visual identity only in MVP.
2. Chooses a commander loadout. Loadouts own mechanical differences; mechanics are never gender-linked.
3. Chooses exactly three commander RAM abilities permitted by the loadout.
4. Chooses Freestyle or Campaign.
5. Chooses a Freestyle point cap, or accepts the selected campaign mission cap.
6. Builds an army within the cap and the ten-unit limit.
7. Reviews validation and deploys.

The frontend gives immediate advisory validation. The Deploy button remains disabled until locally valid, and the backend repeats all validation authoritatively.

### 9.2 Deployment

On deploy, the backend validates and locks prep, creates both forces, selects or generates the map, places objectives, performs automated deployment, creates unit-agent identities, appends opening events, and enters `ACTIVE` battle state.

The operation must be idempotent. A retry after an interrupted response returns the already-created battle rather than creating duplicate units.

### 9.3 Round And Activation Loop

At each round start:

1. Increment round.
2. Refresh commander RAM and expire or tick round-bound effects.
3. Place the commander first in activation order.
4. Roll `1d20 + Speed` for every living non-commander unit.
5. Break ties by higher Speed, then seeded random order.
6. Publish the complete initiative order.
7. Activate the commander, then each living unit once.

The commander is controlled directly through legal UI actions. For agent units, the backend builds a legal option menu, obtains a choice or fallback, revalidates against current state, resolves, publishes events and animation cues, obtains an optional radio line, and advances.

### 9.4 Battle Completion

The backend evaluates victory and defeat after every relevant event batch. Commander destruction always causes friendly defeat. Mission objective rules may add other terminal states. The battle transitions exactly once to `VICTORY`, `DEFEAT`, `DRAW`, `ABORTED`, or `ERROR_RECOVERABLE`, after which combat commands are rejected.

## 10. Rules Summary

The full rules are in `01_RULES_BATTLEFIELD_AND_TERRAIN.md`. Canonical fundamentals are:

- Hex distance and movement use backend axial coordinates.
- A unit begins its activation with one Standard, one Move, and one Minor action.
- Standard may downgrade to Move or Minor; Move may downgrade to Minor. Exchanges are one-for-one. Therefore the maximum is two Move actions or three Minor actions.
- Attack: `3d6 + Attack >= Defense` is a hit.
- Damage: `3d6 + weapon Damage > Armor`; damage equals the amount by which the roll exceeds Armor.
- Units never have negative HP.
- Range, line of sight, occupancy, terrain, resources, and target legality are checked before dice are rolled.
- Commander signal radius is twice RAM capacity, not unspent RAM. Spending RAM does not unexpectedly shrink the network.
- Drones outside signal cannot receive new directives or commander buffs and use a bounded return/defend autonomy menu.

## 11. Forces And Balance

The source values are treated as a first tuning pass, not mathematical truth. Canonical implementation values and filled gaps are in `02_CONTENT_CATALOG_AND_OPPOSITION_BUILDER.md`.

MVP friendly content includes:

- Soldier squads: Infantry, Rangers, Combat Engineers.
- Small drones: One-Way Attack, Direct Attack.
- Medium drones: Support, Flanker.
- Large drones: Blocker, Commander Support, Anti-Armor.
- Commander: one base chassis, visual avatars, six mechanical loadouts, and seven RAM abilities.

Opposition units initially use mechanically equivalent role templates with distinct IDs, names, visuals, audio behavior, and tactical doctrine. Mechanical asymmetry is deferred until parity is proven through automated simulation and playtesting.

## 12. Agent Requirements

- **AGENT-001:** One non-commander unit maps to one persistent agent identity for the battle.
- **AGENT-002:** A squad uses one agent; individual soldiers never receive independent model calls.
- **AGENT-003:** The backend offers only legal or conditionally legal tactical options.
- **AGENT-004:** The model selects an opaque `option_id`; it does not submit raw paths, rolls, damage, or state mutations.
- **AGENT-005:** Only the current initiative actor may commit an action.
- **AGENT-006:** At most five model requests may be in flight, and all early choices are provisional.
- **AGENT-007:** Every provisional choice is revalidated against `state_version` immediately before commit.
- **AGENT-008:** Timeout, invalid output, provider error, and stale choices resolve through one retry or deterministic fallback.
- **AGENT-009:** Friendly agents provide at most one short post-resolution radio sentence by default.
- **AGENT-010:** Opposition agents are radio silent by default; their resolved actions appear as concise system traffic.

See `04_AGENT_ORCHESTRATION_AND_PROMPTS.md`.

## 13. Battlefield And Presentation

The logical battlefield is a 50 by 50 pointy-top axial hex grid. The camera never rotates. The frontend applies a fixed vertical compression and sprite anchoring to create a 2.5D command-table appearance without changing backend geometry.

Required PixiJS layers, back to front:

1. Base ground.
2. Ground decals and roads.
3. Terrain and structures.
4. Hex/path/line-of-sight overlays.
5. Units sorted by projected depth.
6. Effects and projectiles.
7. Selection, labels, objectives, and battlefield HUD.

On the active unit, the UI must distinguish reachable movement, legal targets, weapon range, commander signal radius, objectives, hazards, and blocked cells using shape or icon as well as color.

See `05_RENDERING_ASSETS_AND_AUDIO.md`.

## 14. User Experience

Primary screens are:

- First-run intro/tutorial, dismissible and replayable.
- Mission Prep.
- Battle console.
- Debrief.

The desktop battle console gives the battlefield visual priority, with an initiative strip, selected-unit inspector, command composer, and communications history. Panels adapt or collapse on smaller screens. The player must always know the active actor, remaining actions, current objective, and whether an input was accepted.

All interactive controls require default, hover, pressed, disabled, and focus-visible states plus optional short audio feedback. The interface uses a dark neutral command-console foundation with restrained green, amber, red, cyan, and white semantics. Color alone may not communicate state.

See `06_UX_ACCESSIBILITY_AND_INTERACTION.md`.

## 15. API And Persistence

All new public routes are under `/api/v1`. Commands return an authoritative snapshot or accepted operation ID and emit domain events. Server-to-client updates use a replayable server-sent event stream; client-to-server actions use REST.

The primary persistence records are sessions, session preparation, battles, unit instances, domain events, agent runs, memory blocks, and feedback. Current state may be stored as transactional projections for fast reads, while the append-only event log remains the audit trail.

The inherited `tab1`, `adventure`, `travel`, `monster`, `return-to-moosehearth`, narrative builder, and celebration-song routes are not part of the Drone Commander public API.

See `03_API_DATA_AND_EVENT_CONTRACTS.md`.

## 16. Audio And Media

The app supports background music, UI cues, combat cues, intro media, and TTS for friendly radio lines. Every category has independent volume and mute controls. Spoken messages are queued, cancellable, captioned in the communications log, and must never block initiative progression.

Asset generation may use image, music, voice, and sound-effect services, but runtime code must use provider-neutral manifests and adapters. Every final asset records source, license/usage status, version, and approval state.

## 17. Reliability And Failure Behavior

- Loss of the model provider invokes deterministic tactical AI and continues.
- Loss of TTS displays text and continues.
- Loss of the event stream reconnects with the last event ID and hydrates current state.
- A stale client command receives `409 STATE_VERSION_CONFLICT` and a current snapshot.
- Invalid content prevents startup in development and deployment.
- Animation failure cannot prevent state commitment; the frontend snaps to the authoritative result.
- Refreshing the browser restores the active battle, current activation, events, and queued visual state.

## 18. Delivery Gates

### Gate 0: Repository And Contract Foundation

- Content schemas and validation.
- Canonical IDs and terminology.
- Database migration and session lifecycle.
- Seeded RNG service.
- Event envelope, idempotency, and state versioning.
- Health and boot endpoints.

### Gate 1: Headless Rules Vertical Slice

- 50 by 50 map, deployment, movement, LOS, action economy, attack, damage, destruction, initiative, signal, and annihilation.
- 15-point forces and opposition builder.
- Full battle simulation without frontend or model provider.

### Gate 2: Playable Local Vertical Slice

- Mission Prep, PixiJS battlefield, direct commander activation, initiative UI, communications, animations, debrief.
- Deterministic fallback agents.
- One complete 15-point battle in the browser.

### Gate 3: Model-Agent Integration

- Context builder, legal option menus, queue, revalidation, provider adapter, artifacts, timeouts, fallback, and TTS.
- Battle remains playable with providers deliberately disabled.

### Gate 4: Freestyle MVP Content

- Full roster, point bands, objectives, terrain, maps, loadouts, abilities, ordnance, transport, smoke, mines, and seeded opposition variety.

### Gate 5: MVP Hardening

- Accessibility, responsive layouts, performance, 100-point soak tests, security, telemetry, migration tests, deployment, and complete acceptance suite.

### Gate 6: Campaign

- Six mission definitions, progression, tutorials, campaign debrief, and saved unlock state.

The detailed execution and agent workstream plan is in `09_CURSOR_EXECUTION_PLAN.md`.

## 19. MVP Acceptance Scenarios

The Freestyle MVP is not complete until all scenarios pass:

1. A player creates and refreshes a draft session without losing valid prep.
2. Every allowed point cap can produce at least one legal player force and one legal opposition force.
3. Deploy is idempotent and never creates duplicate units.
4. The commander always acts first; every other living unit acts at most once per round.
5. Standard/Move/Minor downgrades produce no illegal extra action.
6. Movement never crosses blocked cells, exceeds cost, or ends in illegal occupancy.
7. Attacks respect range, LOS, cover, hit threshold, armor threshold, and resource cost.
8. Spending commander RAM never changes signal radius; round start restores RAM.
9. Out-of-signal drones select only legal autonomous options.
10. Destroyed units never act again and cannot receive state-changing commands.
11. A stale queued model choice cannot commit against a changed state version.
12. Provider and TTS outages do not stop the battle.
13. Browser refresh restores the exact active activation and current state.
14. Victory or defeat is emitted once and subsequent combat commands are rejected.
15. A seeded 100-point simulation is reproducible and completes without deadlock.
16. Keyboard-only and reduced-motion users can complete Mission Prep and one battle.
17. All visible state is understandable without relying on color alone.
18. Docker build, backend tests, frontend build, and browser smoke tests pass from a clean checkout.

## 20. Definition Of Done

A feature is done only when:

- Its behavior is represented by a requirement or decision.
- Backend validation and failure behavior exist.
- Unit or integration tests cover its invariants and primary edge cases.
- The frontend exposes loading, success, empty, disabled, and error states where relevant.
- Accessibility and reduced-motion behavior are verified.
- Content and prompts are externalized when designers need to tune them.
- Observability identifies failures without recording secrets or unbounded prompt content.
- Documentation and the decision log are updated.
- The feature works through Docker, not only in an editor-local process.

