# Missing Specification 2: Content Catalog, Balance, And Opposition Builder

This document turns the source roster into a complete, data-driven MVP catalog. All numbers are **TUNING** defaults. IDs and semantic behavior are contractual; values may change through versioned content updates and playtesting.

## 1. Content Rules

- Visual avatar never determines stats. Commander mechanics come from loadout.
- Every unit, weapon, ability, status, faction role, and asset has a stable lowercase `snake_case` ID.
- Runtime instances reference definitions; they do not copy unversioned ad hoc stat blobs.
- The backend validates all cross-references on startup.
- Player and opposition presentation are distinct even when their initial mechanical templates are equivalent.
- Balance values live in content files, not route handlers, React components, prompts, or database migrations.

## 2. Required Unit Definition Shape

Each unit definition contains at least:

```text
id, display_name, side_availability, category, size_class, roles,
point_cost, model_count, speed, attack, defense, armor, hp_per_model,
weapons[], abilities[], movement_traits[], capacity, wreckage_terrain_id,
agent_profile_id, asset_set_id, content_version
```

Derived values such as total remaining HP, living model count, signal status, and effective stats belong to runtime projections.

## 3. Friendly Soldier Squads

| ID | Models | Cost | Speed | Attack | Defense | Armor | HP/model | Weapons | Abilities |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `friendly_infantry_squad` | 10 | 10 | 6 | +0 | 10 | 10 | 1 | Rifle; squad grenade | None |
| `friendly_ranger_squad` | 6 | 6 | 8 | +0 | 11 | 10 | 1 | Rifle | Drop Smoke; Paint Target |
| `friendly_engineer_squad` | 3 | 6 | 5 | +0 | 8 | 13 | 5 | Shotgun | Set Charge; Detect Mine; Deploy Mine |

### 3.1 Soldier Weapons

| ID | Range | Damage | Area | Ammo | Use |
|---|---:|---:|---:|---:|---|
| `rifle` | 10 | +0 | Direct | Unlimited | Each legal living model fires during squad attack |
| `shotgun` | 6 | +2 | Direct | Unlimited | Each legal living model fires during squad attack |
| `squad_grenade` | 4 | +8 | AOE 1 | 1 per squad | One attack from leader; shared squad ordnance |
| `demolition_charge` | Adjacent | +12 | AOE 1 | 2 per engineer squad | Ability use against terrain, objective, or adjacent unit |
| `anti_personnel_mine` | Trigger hex | +8 | AOE 0 | 2 per engineer squad | Hidden hazard; triggers on eligible entry |

### 3.2 Soldier Abilities

**Drop Smoke**  
Minor action, range 6, two charges. Place an AOE-1 smoke effect on a visible hex. Smoke grants occupant light cover and blocks LOS through its hexes. It expires at the start of the Ranger squad's next activation.

**Paint Target**  
Minor action, range 12, requires LOS. Apply `painted` to one visible opposition unit until the start of the Ranger squad's next activation. Friendly drone attacks gain +2 Attack against it, and Airstrike may target it.

**Set Charge**  
Standard action, adjacent target, consumes one demolition charge. Against a destructible terrain/objective, automatically hits and rolls damage. Against a unit, makes a normal attack check.

**Detect Mine**  
Minor action. Reveal hostile mines within four hexes that are not fully blocked by a structure. Detection itself does not remove a mine.

**Deploy Mine**  
Standard action, consumes one mine. Place in an empty adjacent traversable hex not occupied by an objective. The placing side sees the marker; the opposing side sees it only after detection or triggering.

## 4. Friendly Drones

The source document says the shipping game has six drone types but defines seven. Seven catalog entries are canonical.

| ID | Size | Cost | Speed | Attack | Defense | Armor | HP | Weapons | Abilities |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| `friendly_one_way_drone` | Small, flying | 3 | 10 | N/A | 12 | 8 | 1 | None | Self-Destruct |
| `friendly_direct_attack_drone` | Small, flying | 4 | 9 | +0 | 11 | 8 | 1 | Micro-explosive | None |
| `friendly_support_drone` | Medium, ground | 5 | 8 | N/A | 11 | 10 | 5 | None | Resupply Ordnance; Recover Personnel |
| `friendly_flanker_drone` | Medium, ground | 6 | 8 | +0 | 8 | 14 | 5 | Heavy rifle | None |
| `friendly_blocker_drone` | Large, ground | 9 | 6 | +0 | 8 | 20 | 10 | Heavy rifle | Load Squad; Unload Squad |
| `friendly_commander_support_drone` | Large, ground | 11 | 8 | +0 | 8 | 20 | 10 | Heavy rifle | Load Commander; Unload Commander; Signal Relay |
| `friendly_anti_armor_drone` | Large, ground | 12 | 6 | +0 | 8 | 20 | 10 | Heavy rifle; anti-armor missile | None |

The Blocker and Commander Support source speeds were both 10. They are reduced here to 6 and 8 because Speed 10 made the heaviest armored platforms as fast as or faster than expendable flying drones and undermined their listed battlefield roles. This remains a playtestable tuning decision.

### 4.1 Drone Weapons

| ID | Range | Damage | Area | Ammo |
|---|---:|---:|---:|---:|
| `micro_explosive` | 8 | +5 | AOE 1 | Unlimited |
| `heavy_rifle` | 10 | +2 | Direct | Unlimited |
| `anti_armor_missile` | 12 | +10 | Direct | 2 |

Anti-Armor Drones prefer missiles against Armor 14 or higher and use the heavy rifle against soft targets or when missiles are depleted.

### 4.2 Drone Abilities

**Self-Destruct**  
Minor action. The One-Way Drone chooses its current hex or a legal adjacent hex, is destroyed, and automatically creates an AOE-1 Damage +10 detonation. No attack roll is made; each affected model receives a damage roll. Friendly fire applies. The backend must show the predicted area before a human confirmation and must label agent options with friendly-fire risk.

**Resupply Ordnance**  
Minor action, range 2. Restore one spent limited-ammunition charge to a friendly unit, up to that item's starting maximum. A Support Drone may resupply the same unit only once per round.

**Recover Personnel**  
Minor action, range 2, one use per target squad per battle. Restore one destroyed soldier model at 1 HP in the nearest legal formation hex. It cannot affect the commander, drones, a fully defeated squad, or a model destroyed by a mission rule marked unrecoverable.

**Load/Unload Squad**  
Minor actions. The Blocker carries one soldier squad. Loading and destruction behavior follow the transport rules. It cannot carry another large unit or Support Drone.

**Load/Unload Commander**  
Minor actions. The Commander Support Drone carries only the commander. The commander cannot use attacks or RAM abilities while loaded, but may edit directives. If the transport is destroyed, passenger damage applies normally.

**Signal Relay**  
Passive while inside the commander's signal radius. Friendly drones within six hexes of the relay count as in signal. Relays do not chain through other relays.

## 5. Commander

### 5.1 Base Chassis

| Speed | Attack | Defense | Armor | HP | RAM capacity | Base signal radius |
|---:|---:|---:|---:|---:|---:|---:|
| 6 | +0 | 10 | 11 | 5 | 6 | 12 |

The commander costs zero army points and is always required. Avatar choices control portrait, sprite, voice, name, and presentation only.

### 5.2 Commander Loadouts

The player selects one loadout and exactly three RAM abilities. Final stats are base chassis plus modifiers.

| ID | Weapon | Stat modifiers | Passive |
|---|---|---|---|
| `commander_breacher` | Shotgun | Speed -1, Defense -2, Armor +1 | Adjacent friendly infantry gain +1 Defense |
| `commander_recon` | SMG | Speed +1, Attack +2, Defense +2, Armor -1 | Once per activation, preview LOS from one reachable destination |
| `commander_relay` | Carbine | None | Signal radius +2 |
| `commander_electronic_warfare` | PDW | Attack +1, Defense +1, Armor -1 | Satellite Sweep and Signal Jamming each cost 1 less RAM, minimum 1 |
| `commander_air_controller` | Carbine | None | Airstrike costs 5 rather than 6 RAM |
| `commander_guardian` | Shotgun | Speed -1, Defense +1, Armor +2 | Defense Matrix costs 1 less RAM, minimum 1 |

Commander weapon profiles:

| Weapon | Range | Damage | Area |
|---|---:|---:|---|
| Shotgun | 6 | +2 | Direct |
| SMG | 6 | +0 | Direct |
| Carbine | 8 | +1 | Direct |
| PDW | 6 | +0 | Direct |

The Breacher and Recon loadouts preserve the mechanical ideas behind the source's male and female commander blocks while removing gender-linked stats.

### 5.3 RAM Ability Catalog

All RAM abilities are Minor actions.

| ID | RAM | Target | Effect |
|---|---:|---|---|
| `satellite_sweep` | 3 | Battlefield | Reveal stealth and decoy contacts through end of round |
| `airstrike` | 6 | One painted unit/hex | Once per battle; AOE 3, Damage +12; friendly fire applies |
| `signal_jamming` | 3 | Opposition drone within signal | Apply `jammed` through end of round; LOS not required |
| `targeting_assistance` | 3 | Friendly drones in signal | +2 Attack while they remain in signal through end of round |
| `defense_matrix` | 2 | Commander | +4 Defense until next commander activation |
| `call_for_action` | 3 | Friendly soldier units in signal | +2 Speed through end of round |
| `spoof_unit_location` | 2 | Adjacent to friendly unit in signal | Create one decoy contact until attacked, swept, or next round |

Airstrike requires a painted target to make Rangers tactically meaningful and prevent unrestricted map-wide damage. Its once-per-battle limit prevents a full-strength strike every round when RAM refreshes.

A decoy has no HP and cannot contest objectives, block movement, grant cover, or trigger mines. Opposition option menus may target it as if it were the copied unit. Any attack against the decoy automatically removes and reveals it after resources are spent.

## 6. Opposition Catalog

For VS and MVP, opposition mechanics use faction-specific definitions generated from the same role templates and point costs as friendly units. Each definition has a distinct ID, display name, prompt profile, sprite set, color/silhouette language, and radio policy.

Example mapping:

| Friendly template | Opposition ID |
|---|---|
| Infantry | `opposition_line_cell` |
| Rangers | `opposition_recon_cell` |
| Engineers | `opposition_sapper_cell` |
| One-Way Attack | `opposition_impact_drone` |
| Direct Attack | `opposition_burst_drone` |
| Support | `opposition_recovery_drone` |
| Flanker | `opposition_assault_drone` |
| Blocker | `opposition_bulwark_drone` |
| Commander Support | `opposition_relay_carrier` |
| Anti-Armor | `opposition_lancer_drone` |

Opposition units do not receive a commander, RAM abilities, or the player-only Commander Support template in the VS unless a legal force cannot otherwise be built. For MVP, `opposition_relay_carrier` behaves as a durable transport without Signal Relay.

Initial mechanical parity is intentional. It isolates rules and AI quality from faction balance. Asymmetric factions can become new versioned content packs after baseline simulations are stable.

## 7. Army Construction

### 7.1 Player Validation

- Point cap must be one of 15, 25, 40, 55, 75, or 100.
- Commander is mandatory and costs zero.
- At least one non-commander unit is mandatory.
- No more than ten non-commander units.
- Total cost may be below but never above the cap.
- Duplicate units are allowed unless a definition has a `max_per_army` limit.
- One-Way Drones default to `max_per_army = 3` **TUNING**.
- Commander Support Drones default to `max_per_army = 1` **TUNING**.

The opposition builds against the selected cap, not the player's amount spent. Mission Prep must warn that unspent points are a voluntary disadvantage.

### 7.2 Role Tags

Canonical role tags are:

`frontline`, `mobile_damage`, `area_damage`, `anti_armor`, `recon`, `support`, `transport`, `objective`, `screen`, `disposable`.

Units may have multiple roles with weights.

## 8. Deterministic Opposition Builder

The builder must not rely on repeated random guesses. It uses bounded dynamic programming or exhaustive combination search over the small catalog.

### 8.1 Inputs

- selected point cap
- mission restrictions
- faction content pack
- map tags
- deterministic seed
- maximum ten units
- optional doctrine profile

The builder may inspect the player's point total and broad role counts for fairness telemetry, but it must not hard-counter exact units in MVP.

### 8.2 Candidate Generation

1. Enumerate all legal multisets up to ten units and the cap.
2. Prefer exact cap; if impossible, accept the highest reachable total.
3. Apply per-unit limits and mission exclusions.
4. Apply minimum role rules:

| Point band | Minimum composition |
|---|---|
| 15 | One frontline or durable unit; one damage-capable unit |
| 25 | Above plus one mobile, recon, or support role |
| 40 | Above plus at least three distinct primary roles |
| 55 | Above plus one support/recon and one anti-armor or area-damage option |
| 75-100 | At least four distinct roles; no more than 40% of points in one template |

If no force satisfies a soft role rule, relax soft rules in documented order but never break cap, count, or definition limits.

### 8.3 Candidate Scoring

Score candidates by:

- point utilization
- role coverage
- doctrine fit
- map fit without hard counter-picking
- duplicate penalty
- excessive disposable-unit penalty
- ability to damage both soft and armored targets

Choose from the top-scoring band using the supplied seed. Record the seed, candidates considered, selected score, relaxed rules, and final roster for reproducibility.

### 8.4 Guaranteed Fallbacks

Maintain at least one validated authored roster per point cap. If catalog changes make generated candidates invalid, fail content validation in development and use the authored roster only as a production recovery path.

## 9. Tactical Doctrine Profiles

The initial opposition supports three data-driven doctrine profiles:

- `balanced`: objectives, cover, damaged targets, and asset preservation.
- `aggressive`: close distance, pressure commander, accept moderate exposure.
- `defensive`: hold cover, protect support, contest objectives, avoid unfavorable trades.

Doctrine adjusts tactical-option scores; it never creates illegal options or modifies unit stats.

## 10. Balance Process

Balance begins with deterministic fallback AI so model variation does not obscure rules defects.

For every point cap, run seeded mirror and mixed-roster simulations and record:

- win rate by starting side and doctrine
- rounds to completion
- damage per point
- survival by role
- objective score progression
- first-round losses
- unused ammunition and abilities
- commander deaths
- agent fallback frequency

Initial targets are 45-55% friendly wins in mirrored automated tests, fewer than 10% battles decided by the end of round one, and no single unit template present in more than 70% of top-scoring generated forces. These are diagnostic targets, not promises of perfect competitive balance.

## 11. Content Acceptance

- Every point cap has at least five valid generated opposition rosters before seeded selection.
- Every ability has explicit action, target, range, cost, duration, stacking, and failure rules.
- Every limited resource has an initial maximum and resupply behavior.
- Every unit has a legal fallback action when isolated, unarmed, out of signal, or unable to reach a target.
- Every definition resolves its prompt and asset references.
- Catalog changes produce a content-version bump and migration/compatibility decision.

