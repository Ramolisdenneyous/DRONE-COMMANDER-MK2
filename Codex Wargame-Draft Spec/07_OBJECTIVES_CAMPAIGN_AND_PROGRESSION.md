# Missing Specification 7: Objectives, Campaign, And Progression

Objectives are backend state machines built from versioned mission data. Campaign is deliberately downstream of the Freestyle MVP; it reuses the same rules rather than adding mission-specific code paths.

## 1. Objective Model

Every objective instance contains:

```text
objective_instance_id, definition_id, type, status,
hexes_or_zone, eligible_sides, visible_state, progress,
scoring_timing, completion_rule, failure_rule, terminal_effect,
event_history_refs
```

Canonical status:

```text
INACTIVE -> ACTIVE -> COMPLETED | FAILED
```

Contested/control ownership is progress state, not terminal status.

## 2. Evaluation Timing

Objectives declare one or more evaluation moments:

- after unit movement
- after action resolution
- after unit destruction
- after activation
- at round end
- at battle start for setup validation

Evaluation occurs inside the same atomic event batch as the triggering mechanical change. Terminal battle state is evaluated after all objective transitions in that batch.

## 3. Control And Contesting

A unit controls an objective when at least one eligible living model occupies or is within the definition's radius. A squad contributes one control unit regardless of living model count unless a mission explicitly uses model strength.

If both sides have eligible units in the control radius, the objective is contested and neither side gains round-end progress. Loaded units, decoys, mines, and destroyed units do not control.

Default control radius is one hex **TUNING**. A side must hold through the round-end evaluation to gain one progress step.

## 4. Objective Templates

### 4.1 Annihilation

- Friendly completion: all opposition units defeated.
- Friendly failure: commander defeated.
- Use: VS and default Freestyle.
- Tie: simultaneous completion/failure in one batch produces Draw.

### 4.2 Control Points

- One to three control zones.
- Gain one score per controlled zone at round end.
- Default victory at five score **TUNING** or first to hold the primary zone for two consecutive round ends.
- Commander defeat remains immediate failure.
- Optional round limit resolves by score, then surviving point value, then Draw.

### 4.3 Extraction

- One designated friendly unit/object enters extraction zone and spends a Minor action to extract.
- Extracted unit is removed from battle occupancy but remains alive.
- Completion may require commander, asset, or a minimum number of squads.
- Failure occurs if a required asset is destroyed or commander dies.
- Opposition may block/contest the zone according to mission data.

### 4.4 Escort

- An escort asset follows normal unit/transport rules and has a destination zone.
- Completion when the living asset extracts.
- Failure if asset or commander is destroyed.
- Escort movement may be player-agent controlled or mission-scripted; the mode is explicit in data.

### 4.5 Demolition

- Target structure has Armor, HP, and optional charge-only vulnerability.
- Completion when destroyed or successfully charged.
- Failure at round limit, engineer loss if engineer-required, or commander death.

### 4.6 Holdout

- Friendly side survives through a named round while controlling or protecting a zone.
- Reinforcement waves are mission events, not exceptions in core initiative code.
- Completion after final round-end evaluation.

## 5. Composite Victory Conditions

Mission data combines objective predicates using explicit `all`, `any`, and `at_least` groups. Avoid arbitrary executable expressions in content.

Example concept:

```text
victory: all(extract(commander), at_least(1, extract(intel_carriers)))
defeat: any(commander_destroyed, intel_assets_all_destroyed, round_limit_exceeded)
```

The validator detects unknown objective IDs, impossible setup, circular dependencies, and terminal conditions with no reachable outcome.

## 6. Freestyle Objective Selection

Freestyle MVP supports:

- Annihilation on all maps.
- Control Points on maps with validated control zones.
- Extraction on maps with validated routes and zones.

The player may choose objective type or Random. Random selection uses the battle seed and filters by map compatibility. Opposition doctrine receives the same public objective rules.

## 7. Campaign Structure

Campaign is six linked missions:

| Mission | Points | Working title | Primary teaching/system focus |
|---|---:|---|---|
| 1 | 15 | Signal On | Movement, attack, commander safety, signal radius |
| 2 | 25 | Painted Lines | Cover, smoke, target painting, Control Points |
| 3 | 40 | Dead Channel | Engineers, mines, jamming, restoring a relay |
| 4 | 55 | Narrow Corridor | Transport, escort, extraction, unit-specific directives |
| 5 | 75 | Ghost Grid | Stealth, decoys, satellite sweep, airstrike timing |
| 6 | 100 | Command Collapse | Full combined arms, multiple objectives, opposition command node |

Titles are working content and may change without altering mission IDs.

## 8. Mission Specifications

### Mission 1: Signal On

- Point cap: 15.
- Prepared map with clear lanes and obvious cover.
- Player content: commander, Infantry, three VS drones.
- Objective: secure the central uplink for two consecutive round ends, or eliminate opposition.
- Failure: commander destroyed.
- Tutorials: camera, select commander, move, attack, signal overlay, directive, initiative.
- Opposition: balanced 15-point force; no mines, stealth, transport, or AOE-heavy opening placement.

### Mission 2: Painted Lines

- Point cap: 25.
- Unlock Rangers and Direct Attack Drone if not already available.
- Objective: score five control points across two zones.
- Tutorials: light/heavy cover, smoke, Paint Target, AOE confirmation.
- Opposition doctrine: defensive around one zone, mobile pressure around the other.
- Failure: commander destroyed or opposition reaches score target.

### Mission 3: Dead Channel

- Point cap: 40.
- Unlock Engineers, Support Drone, and electronic-warfare commander loadout.
- Objective: detect and clear a route, plant a charge on a jammed relay, then hold it for one round.
- Tutorials: mines, detection, demolition, resupply, jamming/autonomy.
- Failure: commander destroyed, relay rendered unrecoverable, or round limit exceeded.

### Mission 4: Narrow Corridor

- Point cap: 55.
- Unlock Blocker and Commander Support Drones.
- Objective: escort a communications package or designated squad to extraction.
- Tutorials: load/unload, transport destruction risk, unit-specific directives, screening.
- Opposition doctrine: aggressive flank pressure without hidden reinforcements on the extraction zone.
- Failure: commander or escorted asset destroyed, or round limit exceeded.

### Mission 5: Ghost Grid

- Point cap: 75.
- Unlock full RAM catalog and Anti-Armor Drone.
- Objective: identify the real signal emitter among decoys, paint it, and destroy it.
- Tutorials: stealth, decoys, Satellite Sweep, Airstrike, ammunition preservation.
- Opposition doctrine: defensive deception with armored screen.
- Failure: commander destroyed or all scanning/painting capability lost with no alternate completion path.

The mission must always provide an alternate manual destruction route so losing Rangers does not make the battle unwinnable.

### Mission 6: Command Collapse

- Point cap: 100.
- Full friendly roster and loadouts.
- Objectives: capture two relay zones, then demolish the opposition command node or hold both relays through a final round.
- Tutorials: none beyond contextual reminders.
- Opposition: full combined-arms force and scripted reinforcement event from legal deployment cells. It still has no full enemy Commander/RAM system; the command node is an objective asset.
- Failure: commander destroyed, opposition reaches its score threshold, or round limit exceeded.

## 9. Tutorial System

Tutorials are data-driven triggers and overlays, not hardcoded mission branches. A tutorial step declares:

```text
id, trigger event/predicate, target UI semantic ID, title, concise body,
allowed dismiss behavior, completion event/predicate, repeat policy
```

Tutorials pause before input when necessary but never during committed animation. They are keyboard/screen-reader accessible, have captions for media, and can be disabled or replayed.

Contextual reminders may highlight a relevant legal control. They cannot invent an action or bypass backend legality.

## 10. Campaign Persistence

Recommended records:

- `campaign_runs`: campaign ID/version, session/player scope, current mission, status, difficulty, timestamps.
- `campaign_mission_results`: mission ID/version, result, battle ID, score, losses, rounds, completed objectives.
- `campaign_unlocks`: unlocked units/loadouts/abilities and source mission.

The first campaign has no persistent HP, ammunition loss, soldier permadeath, XP, currency, or inventory. Every mission begins with catalog base state. This avoids an unbalanced strategic layer before the tactical game is proven.

Victory unlocks the next mission. Defeat allows retry with the same army/map seed or rebuild with a new seed where mission rules permit. Completed missions remain replayable.

## 11. Campaign Narrative Boundary

Mission data may reference briefing, intro, objective, event, and debrief text/audio IDs. Narrative content does not embed Python conditions or change stats. Scripted events use validated triggers and action types such as spawn at legal zone, reveal objective, update directive, play media cue, or add communication.

Fictional factions and locations must avoid direct copies of current combatants, real insignia, or claims about real events. The campaign can carry political themes through fictional institutions and consequences without turning present conflicts into target practice.

## 12. Difficulty

Initial difficulty modifies opposition doctrine and optional force handicap through explicit content values, not hidden dice cheating.

- `assisted`: opposition cap reduced by up to 10%, more tutorial reminders, no change to core rolls.
- `standard`: equal selected point cap.
- `veteran`: equal cap with stronger doctrine weights and less conservative fallback; no secret stat bonuses.

Difficulty is stored in mission/battle lock context and reported in Debrief.

## 13. Objective And Campaign Acceptance

- Each objective can be simulated headlessly to victory, defeat, and draw where allowed.
- Contested control never scores for both sides.
- Terminal result emits exactly once.
- Every campaign mission validates at startup and has a reachable success path after optional units are lost.
- Tutorials can be skipped without blocking mechanics.
- Restarting a mission does not duplicate unlocks or results.
- A campaign save survives browser refresh and backend restart.
- Campaign content adds no mission-specific mutation route or unvalidated script execution.

