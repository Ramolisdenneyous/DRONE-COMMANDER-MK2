# Missing Specification 1: Rules, Battlefield, And Terrain

This document is the canonical mechanical rules contract. Numbers marked **TUNING** belong in content data; algorithms and invariants belong in backend code.

## 1. Rules Principles

1. The backend calculates legality before presenting actions.
2. No roll occurs for an illegal action.
3. The same seed and ordered command sequence produce the same result.
4. Mechanical resolution is complete before narration or animation begins.
5. Presentation can interpolate a result but cannot alter it.

## 2. Dice And Randomness

The rules engine uses a session-scoped seeded random-number generator. Every random operation records its purpose and result in the event batch.

### 2.1 Core Checks

- Attack check: `3d6 + Attack >= effective Defense`.
- Damage check: `3d6 + weapon Damage > effective Armor`.
- Damage dealt: `damage total - effective Armor`.
- Initiative: `1d20 + Speed`.

A hit ties Defense successfully. A damage roll must exceed Armor; a tie deals zero damage. Dice are never rounded to an average during play. The 3d6 average of 10.5 is a balance reference only.

### 2.2 RNG Recording

Each roll event includes:

- `rng_index`
- `dice_expression`
- individual die results
- modifiers
- total
- target number, when applicable
- success/failure
- reason

Tests may inject fixed rolls without changing production rule code.

## 3. Hex Battlefield

### 3.1 Logical Coordinates

The backend uses pointy-top axial coordinates `(q, r)` with `0 <= q < 50` and `0 <= r < 50`. It may derive cube coordinate `s = -q-r` for distance and line algorithms.

Canonical distance:

```text
distance(a, b) = (abs(dq) + abs(dr) + abs(ds)) / 2
```

Canonical neighbor directions:

```text
(+1, 0), (+1, -1), (0, -1), (-1, 0), (-1, +1), (0, +1)
```

Coordinates in storage and APIs remain numeric. The UI may show friendly labels, but labels are never parsed back into game logic.

### 3.2 Fixed Camera Projection

The frontend maps axial coordinates to normal pointy-top world coordinates, then applies a fixed vertical scale for the 2.5D appearance. Camera rotation is not supported. Visual compression never changes pathing, range, or line of sight.

### 3.3 Occupancy

- Every single-model unit occupies one hex in MVP, including large drones.
- Every living soldier model occupies one distinct hex.
- Two solid models may not end movement in the same hex.
- Friendly models may path through friendly occupied hexes at +1 movement cost but may not stop there.
- Models may not path through opposition-occupied hexes.
- Objectives and non-solid markers do not block occupancy unless their content definition says so.
- Wreckage is terrain, not a living unit. Its definition decides whether it blocks movement or supplies cover.

Multi-hex vehicles are deferred. Art may visually extend beyond the logical footprint but must preserve a readable base marker.

## 4. Round Structure

### 4.1 Round Start Order

1. Increment the round number.
2. Expire effects whose duration ended at the previous round boundary.
3. Tick ongoing effects in a stable effect-ID order.
4. Restore commander RAM to capacity.
5. Recalculate derived state such as signal and visibility.
6. Put the living player commander first.
7. Roll initiative for every living non-commander unit.
8. Sort descending by total, then Speed, then seeded random tie break.
9. Emit one atomic `round_started` event batch containing the final order.

### 4.2 Activation

At activation start, the actor receives:

- one Standard action
- one Move action
- one Minor action

Actions may be taken in any order. Standard may be downgraded one-for-one to Move or Minor. Move may be downgraded one-for-one to Minor. No action may be upgraded.

Legal maximums include:

- one Standard, one Move, one Minor
- two Move, one Minor
- one Move, two Minor
- three Minor

A unit may voluntarily end activation with actions unspent. Actions do not carry between activations.

### 4.3 Commander Directives

During commander activation, the player may update one global directive and any unit-specific directives. Directives do not consume actions because they express intent and do not guarantee a mechanical benefit. They lock when the commander ends activation and remain active until replaced or made irrelevant.

Mechanical command abilities, attacks, movement, and RAM powers consume the listed actions normally.

### 4.4 Activation Completion

An activation completes when the actor ends voluntarily, has no legal/useful actions and invokes hold, or a timeout fallback completes it. The backend marks the activation exactly once. A destroyed or disabled actor cannot begin an activation.

## 5. Movement And Pathfinding

### 5.1 Move Budget

A Move action grants movement points equal to current Speed. A unit may take two Move actions by downgrading Standard, but each is a separate movement transaction. A single Move action cannot be split around another action.

Movement cost is paid when entering a hex. The starting hex costs zero.

### 5.2 Pathfinding

Use A* over axial neighbors with hex distance as the heuristic. A legal path must:

- remain on the map
- have total cost no greater than the action budget
- respect terrain and occupancy
- end in legal occupancy
- respect unit movement traits such as flying

When several paths have equal cost, use a stable direction order so seeded simulations remain reproducible.

### 5.3 Zones Of Control

Zones of control and reaction attacks are deferred. Enemy adjacency does not stop movement in MVP unless an ability explicitly creates a blocking effect.

### 5.4 Flying

Small flying drones ignore ground difficult-terrain costs and may cross low obstacles and occupied hexes. They may not end on a blocked structure hex and cannot cross terrain tagged `air_blocking`. Mines do not trigger against flying units unless tagged anti-air.

### 5.5 Squad Movement

A soldier squad has one leader/anchor model: the highest-numbered living model. The player or agent selects an anchor destination, not individual destinations.

The backend then assigns each follower a legal destination using these priorities:

1. Within five hexes of the leader, as required by the source design.
2. Reachable within that model's movement budget.
3. Preserve relative formation when practical.
4. Prefer cover consistent with the chosen tactical option.
5. Avoid hazards and blocking firing lanes.
6. Use stable model-number order for ties.

The movement option is not offered unless every living model can receive a legal final position. The UI previews the complete formation before confirmation. Movement animates leader first, with followers starting in a short stagger, but commits as one atomic backend result.

If the leader dies, the highest-numbered survivor becomes leader immediately.

## 6. Range, Visibility, And Line Of Sight

### 6.1 Range

Weapon and ability range use hex distance between source and target hexes, inclusive of the target and excluding the source. A range-10 weapon may target a hex at distance 10.

### 6.2 Line Of Sight

Use a deterministic cube-line interpolation between source and target hex centers. The target hex is visible if no intermediate hex contains terrain tagged `blocks_los` or an effect that blocks LOS.

For ambiguous lines that pass exactly along a hex edge, evaluate both epsilon-offset cube lines. LOS exists if either line is clear. This prevents arbitrary left/right artifacts.

Living units do not block LOS in MVP. Structures, walls, dense terrain, and smoke can.

### 6.3 Squad Visibility

A squad is visible if at least one living model is visible. An attack against a squad selects a visible model. Batch squad attacks assign each attacker to the nearest legal visible model, preferring already-damaged multi-wound models only when the tactical option explicitly requests focus fire.

### 6.4 Cover

Cover modifies Defense, not Armor.

- Light cover: `+2 Defense` **TUNING**.
- Heavy cover: `+4 Defense` **TUNING**.

A target receives cover when a cover-providing edge or adjacent terrain lies on the final segment of the line from attacker to target. A target occupying a terrain hex receives that terrain's occupant cover value. Multiple cover sources do not stack; use the highest.

AOE splash damage ignores cover unless the effect definition says otherwise. Elevation rules are deferred.

## 7. Attacks And Damage

### 7.1 Attack Resolution Order

1. Validate actor, action, weapon, target, resources, range, LOS, and friendly-fire confirmation.
2. Spend the action and required ammunition or charges.
3. Roll attack.
4. On a miss, emit miss events and stop unless the weapon defines scatter. MVP weapons do not scatter.
5. On a hit, identify affected models.
6. Roll damage separately for each affected model.
7. Apply HP changes without going below zero.
8. Mark destroyed models and units.
9. Apply statuses and secondary effects.
10. Recalculate occupancy, objectives, victory, and defeat.
11. Emit animation cues derived from the committed result.

### 7.2 Direct Attacks

A direct attack targets one visible model or single-model unit. Excess damage does not spill into another model.

### 7.3 Squad Attacks

Unless a weapon or ability says otherwise, every living model in an attacking squad that has range and LOS makes one attack with its equipped weapon. The backend resolves these as a batch with stable attacker-model order. The UI may animate shots in a staggered volley.

Models without a legal target do not fire. One squad attack consumes one Standard action for the whole squad, not one action per model.

### 7.4 Area Of Effect

`AOE N` means all hexes with distance `<= N` from the impact hex. The attacker first makes one attack check against the primary target. On a miss, there is no impact in MVP. On a hit, each solid model in the area receives a separate damage roll, including friendly models and the attacker if present.

AOE attacks require a confirmation when friendlies are in the predicted area. Agents are not offered high-friendly-fire options unless their doctrine permits desperation and no safer option exists.

### 7.5 Destruction

A model at zero HP is destroyed. A squad is defeated when all models are destroyed. A single-model unit is defeated at zero HP. Defeated units are removed from future initiative, queued calls, target lists, and directives. Wreckage behavior comes from the unit content definition.

The player commander reaching zero HP ends the battle in defeat after the current atomic event batch.

## 8. Resources, Abilities, And Statuses

### 8.1 RAM And Signal

The commander has RAM capacity 6 **TUNING**. Current RAM refreshes to capacity at round start. Abilities spend current RAM and cannot overdraw it.

Signal radius is `2 * RAM capacity`, normally 12 hexes. Spending RAM does not reduce signal radius. This follows the command-stat inspiration while avoiding surprising mid-round disconnections.

Friendly drones inside signal may receive directives, commander buffs, and normal agent options. A drone outside signal:

- cannot receive a newly issued directive
- cannot gain a new commander aura or targeted RAM effect
- receives only `return_to_signal`, `take_cover`, `defend_self`, `continue_current_objective`, or `hold` options that are legal
- retains already-committed effects until their normal expiration unless the effect requires continuous signal

Soldier squads do not require signal for basic action but cannot receive new unit-specific directives while outside signal. The global directive they last received remains their intent.

### 8.2 Standard Status Definitions

| Status | Mechanical effect | Default duration |
|---|---|---|
| `painted` | Allied drone attacks gain +2 Attack; enables Airstrike | Until painter's next activation |
| `smoke_concealment` | Occupant gains light cover; smoke hex blocks LOS through it | Start of source's next activation |
| `jammed` | Drone gets -2 Attack and cannot use active special abilities | End of current round |
| `targeting_assisted` | +2 Attack for friendly drones in signal when applied | End of current round |
| `defense_matrix` | Commander gains +4 Defense | Start of next commander activation |
| `call_for_action` | Friendly soldier units in signal gain +2 Speed | End of current round |
| `stealthed` | Cannot be targeted beyond range 5 unless revealed | End defined by source |
| `revealed` | Ignores stealth and identifies decoy contacts | End of current round |
| `loaded` | Unit is removed from map and attached to transport | Until unloaded or transport destroyed |

Effects of the same ID do not stack unless explicitly marked stackable. Reapplication refreshes duration.

### 8.3 Transport

A unit loads when adjacent to a compatible transport, both are alive, and the listed Minor action is available. The passenger is removed from occupancy and attached to the transport. A loaded unit cannot activate independently; if its initiative arrives, it is skipped and marked carried.

Unload is a Minor action and places the passenger in a legal adjacent formation. If no legal formation exists, unload is unavailable.

If a transport is destroyed, place passengers in nearest legal adjacent hexes and apply one `3d6 + 0` damage roll against Armor to each model **TUNING**. If placement is impossible, expand the search radius deterministically. A passenger is never silently deleted.

### 8.4 Mines

Mines are hidden hazard markers with owner, hex, trigger tags, and damage profile. Deployment requires a legal adjacent empty hex and consumes ordnance. Detection reveals mines within the ability radius. An eligible enemy entering the hex stops movement, reveals the mine, and resolves its attack before movement may continue.

## 9. Terrain Catalog

Terrain mechanics are defined in data with these minimum fields: ID, display name, movement cost by movement trait, occupant cover, LOS behavior, solid occupancy, destructibility, HP/Armor if destructible, hazard behavior, visual asset ID, and tags.

Canonical MVP terrain:

| Terrain | Ground cost | Flying cost | Cover | LOS | Occupancy |
|---|---:|---:|---|---|---|
| Clear ground | 1 | 1 | None | Clear | Allowed |
| Road | 1 | 1 | None | Clear | Allowed |
| Rubble | 2 | 1 | Light | Clear | Allowed |
| Crater | 2 | 1 | Light | Clear | Allowed |
| Low barrier | 1 | 1 | Heavy across barrier edge | Clear | Allowed adjacent, not on barrier edge |
| Wreckage | 2 | 1 | Heavy | Clear | Allowed if definition permits |
| Water/mud | 2 | 1 | None | Clear | Ground allowed |
| Wall | Blocked | 1 if low, blocked if tall | Heavy | Blocked | Not allowed |
| Building footprint | Blocked | Blocked | Heavy | Blocked | Not allowed |
| Dense structure | Blocked | Blocked | Heavy | Blocked | Not allowed |
| Smoke effect | 1 | 1 | Light to occupant | Blocks through | Allowed |

Doors, destructible buildings, elevation, interiors, ladders, and bridges are deferred unless a campaign mission explicitly requires them.

## 10. Deployment

Friendly deployment uses `r = 45..49`; opposition uses `r = 0..4`. A map may override edges but must supply two non-overlapping legal zones.

Automated deployment priorities:

1. Commander in rear-center legal cover when available.
2. Durable frontline units toward the forward edge.
3. Infantry in central or cover-adjacent positions.
4. Support behind frontline units.
5. Fast drones on flanks.
6. Long-range units with useful initial lanes that do not create unavoidable first-activation kills.

Placement uses stable role order plus a seed. Squads require a complete legal formation. Opposition uses equivalent role logic with its own edge.

## 11. Maps And Generation

### 11.1 Vertical Slice

The VS uses one authored map. This removes generator uncertainty while movement, LOS, cover, deployment, agents, and rendering are proven.

### 11.2 Freestyle MVP

MVP generation is seeded and template-driven, not unconstrained noise:

1. Choose a biome/base texture set.
2. Place road or lane templates.
3. Place structure clusters from validated stamps.
4. Add cover and ground-detail stamps.
5. Place objectives subject to mission rules.
6. Validate deployment capacity, connectivity, objective reachability, cover distribution, and LOS fairness.
7. Retry with a derived seed up to a fixed limit.
8. Fall back to a prepared map if validation still fails.

Map validation must prove:

- At least one ground path connects deployment zones.
- Every objective is reachable by both sides.
- Each zone has enough legal cells for ten units including squad formations.
- No objective starts inside a deployment zone unless mission rules require it.
- Blocking terrain cannot isolate an unmarked region.
- Neither commander deployment center has an unobstructed direct-fire lane to the other deployment center.
- Terrain IDs and assets resolve.

## 12. Objectives And Terminal Conditions

The VS objective is Annihilation: friendly victory when every opposition unit is defeated; friendly defeat when the commander is defeated. A round limit may produce a draw in automated tests but is disabled for normal VS play.

Freestyle MVP also supports Control and Extraction as defined in `07_OBJECTIVES_CAMPAIGN_AND_PROGRESSION.md`.

Terminal evaluation occurs after an atomic event batch, never halfway through damage application. If both sides meet terminal conditions in the same batch, mission-specific precedence applies; otherwise the result is a draw.

## 13. Mechanical Invariants

The backend must assert or continuously test:

- HP and resources remain within `[0, maximum]`.
- A solid hex has no more than one solid model.
- Every living deployed model has an in-bounds position or is validly loaded.
- Every initiative actor maps to one living, non-loaded unit.
- No unit completes more than one activation per round.
- No state version is committed twice.
- A destroyed unit never owns pending provider work that can commit.
- An action never spends more actions, movement, ammunition, charges, or RAM than available.
- Event sequence numbers are unique and increasing per session.
- A terminal battle accepts no further combat mutation.

## 14. Rules Acceptance Tests

At minimum, automated tests cover threshold ties, action downgrades, two-Move limits, terrain costs, flying, occupancy, squad formation, LOS edge ambiguity, cover, direct and AOE damage, friendly fire, status duration, RAM refresh, signal loss behavior, transport destruction, mines, initiative ties, deployment capacity, seeded generation, simultaneous terminal conditions, and every invariant above.

