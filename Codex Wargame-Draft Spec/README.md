# Drone Commander Implementation Specification

Status: Draft handoff package  
Source: `Drone Commander (4).txt`  
Prepared for: Cursor planning mode and implementation agents

## Purpose

This folder converts the original design document into an implementation-oriented specification. It preserves the game's central fantasy and intended systems while separating confirmed requirements, implementation decisions, tuning values, deferred features, and unresolved product choices.

## Authoritative Reading Order

When documents conflict, use this order:

1. `10_DECISIONS_ASSUMPTIONS_AND_OPEN_QUESTIONS.md`
2. `00_MASTER_IMPLEMENTATION_SPEC.md`
3. The focused specification for the relevant subsystem
4. `09_CURSOR_EXECUTION_PLAN.md`
5. The original `Drone Commander (4).txt`

The original document remains valuable design history, but it is not an implementation contract after this handoff.

## Document Map

| File | Purpose |
|---|---|
| `00_MASTER_IMPLEMENTATION_SPEC.md` | Product, scope, architecture, functional requirements, and release gates |
| `01_RULES_BATTLEFIELD_AND_TERRAIN.md` | Canonical combat, movement, line of sight, squads, terrain, deployment, and map rules |
| `02_CONTENT_CATALOG_AND_OPPOSITION_BUILDER.md` | Canonical MVP roster, abilities, loadouts, ammunition, and deterministic enemy-force construction |
| `03_API_DATA_AND_EVENT_CONTRACTS.md` | Domain entities, API surface, event stream, persistence, idempotency, and error contracts |
| `04_AGENT_ORCHESTRATION_AND_PROMPTS.md` | Bounded agent decisions, prompt assembly, activation queue, fallbacks, timeouts, and radio replies |
| `05_RENDERING_ASSETS_AND_AUDIO.md` | PixiJS scene model, coordinate projection, terrain assets, animation contracts, audio, and asset pipeline |
| `06_UX_ACCESSIBILITY_AND_INTERACTION.md` | Screen flows, responsive layout, input behavior, accessibility, feedback, and failure states |
| `07_OBJECTIVES_CAMPAIGN_AND_PROGRESSION.md` | Objective state machines and the six-mission campaign framework |
| `08_TESTING_SECURITY_OBSERVABILITY_AND_DEPLOYMENT.md` | Test strategy, quality gates, security, privacy, cost controls, telemetry, Docker, and Railway |
| `09_CURSOR_EXECUTION_PLAN.md` | Ordered implementation plan, agent workstreams, checkpoints, and definition of done |
| `10_DECISIONS_ASSUMPTIONS_AND_OPEN_QUESTIONS.md` | Resolved contradictions, assumptions, tuning flags, and decisions still reserved for Raymond |
| `11_ORIGINAL_SPEC_ASSESSMENT.md` | Evaluation of the source document and an explanation of the rewrite |

## Instructions To The Implementing Agent

1. Inspect the actual repository before editing. Treat existing code and tests as evidence; do not assume the inherited Story Engine layout is unchanged.
2. Create an implementation plan tied to requirement IDs and delivery gates in the master spec.
3. Complete one gate at a time. A gate is not complete until its automated tests pass and its acceptance scenario works through the UI.
4. Keep game content, agent prompts, rules, and presentation assets in separate modules. Designers must be able to tune content without editing orchestration code.
5. Keep the backend authoritative. The browser and language models may request actions but never declare mechanical results.
6. Use deterministic seeds for tests, force building, maps, and dice when a test seed is supplied.
7. Record assumptions in the decision log. Do not silently invent gameplay rules.
8. Preserve unrelated user changes in a dirty worktree.

## Scope Labels

- **VS**: 15-point vertical slice used to prove the architecture.
- **MVP**: Complete Freestyle release from 15 to 100 points.
- **Campaign**: Six linked missions built after the Freestyle MVP is stable.
- **Later**: Multiplayer, advanced fog of war, full enemy command networks, and other stretch goals.

## Requirement Language

- **Must** means required for the named delivery gate.
- **Should** means expected unless repository evidence makes a different implementation materially safer.
- **May** means optional.
- Values marked **TUNING** are canonical starting values stored in content data and expected to change through playtesting.

