# Decisions, Assumptions, And Open Questions

This is the highest-authority document in the package. Add dated entries rather than silently changing resolved behavior.

## 1. Resolved Decisions

### D-001: Scope Has Three Named Gates

**Decision:** "VS" is the fixed 15-point technical vertical slice; "MVP" is complete Freestyle at 15-100 points; Campaign is the six-mission release after MVP.  
**Reason:** The source used MVP for both a one-week 15-point test and a content-complete Freestyle game. Separate names make planning and acceptance possible.

### D-002: Backend Is Mechanical Authority

**Decision:** Browser, model agents, animation, and narration request or display outcomes; only backend domain code validates and commits them.  
**Reason:** This is the strongest architectural principle in the source and is essential to prevent model hallucination or stale clients from corrupting play.

### D-003: Canonical Stat Terms

**Decision:** Use `Defense`, `Armor`, and `Minor action`.  
**Reason:** The source alternated among Defiance/Defence/Defense, Armer/Armor, and Swift/Minor. One vocabulary is required across data, API, UI, prompts, and tests.

### D-004: Avatar And Mechanics Are Separate

**Decision:** Commander avatars are visual/voice identity. Loadouts determine stats, weapons, and passives.  
**Reason:** The source gave male and female avatars different combat stats while also saying MVP avatars may be mostly visual. Gender should not silently select a mechanical chassis; the original stat ideas remain as Breacher and Recon loadouts.

### D-005: Seven Drone Catalog Entries

**Decision:** The Freestyle MVP has seven drone entries.  
**Reason:** The summary promised six but the roster defines One-Way, Direct Attack, Support, Flanker, Blocker, Commander Support, and Anti-Armor.

### D-006: Signal Uses RAM Capacity

**Decision:** Signal radius is twice RAM capacity; spending current RAM does not shrink it.  
**Reason:** This matches the likely tabletop inspiration and avoids a surprising cascade where using a command ability disconnects drones in the same turn. Current RAM still gates ability spending.

### D-007: Action Downgrades Are One-For-One

**Decision:** Standard downgrades to one Move or one Minor; Move downgrades to one Minor.  
**Reason:** This produces the source's stated maxima of two Moves or three Minors without letting one Standard create two additional actions by itself.

### D-008: Agents Select Bounded Option IDs

**Decision:** Models select one backend-issued tactical option ID through one schema/tool. They do not submit raw move/attack calls or calculate board state.  
**Reason:** The source correctly says the agent should choose tactical intent. Opaque options make that boundary enforceable, testable, and resilient to prompt injection.

### D-009: Opposition Is Radio Silent By Default

**Decision:** Friendly agents may speak one post-resolution line. Opposition actions use concise system traffic unless a mission explicitly enables intercepted speech.  
**Reason:** The source includes enemy reply examples but later says opposition is largely silent. Silence preserves battle tempo and avoids revealing intent/hidden information.

### D-010: Prepared Map Before Procedural Generation

**Decision:** VS uses one authored 50 by 50 map. MVP adds seeded template-based generation with validation and prepared fallback.  
**Reason:** Map generation multiplies pathing, fairness, and asset uncertainty. A prepared map proves the combat loop first without abandoning the procedural goal.

### D-011: Deterministic Fallback Is Mandatory

**Decision:** Every agent activation can resolve through deterministic tactical AI. Model and TTS providers are optional enhancement layers.  
**Reason:** Provider outage, cost, rate limits, invalid output, and test reproducibility must not stop a turn-based game.

### D-012: Content And Prompts Are Versioned Data

**Decision:** Units, weapons, abilities, terrain, maps, missions, factions, prompts, and asset references live in validated, human-editable content files.  
**Reason:** Raymond explicitly wants modular files that creative, balance, and technical agents can edit independently.

### D-013: REST Commands Plus SSE Events

**Decision:** Use REST for client commands/snapshots and replayable server-sent events for ordered server-to-client battle updates.  
**Reason:** The client mostly receives authoritative updates; REST+SSE is simpler than bidirectional sockets, works with idempotent commands, and supports reconnect/replay.

### D-014: Events Plus Transactional Projections

**Decision:** Store append-only domain events and current projections in the same transaction, with an outbox after commit.  
**Reason:** Pure event sourcing would add unnecessary first-release complexity, while projection-only state would weaken replay, audit, agent context, and reconnect behavior.

### D-015: Campaign Has No Persistent Tactical Attrition Initially

**Decision:** No permadeath, persistent HP/ammo, XP, currency, or inventory in the first campaign.  
**Reason:** Those systems create a second balance economy and failure spiral before the tactical game is proven. Mission unlocks and results provide initial progression.

### D-016: Fictional Conflict Presentation

**Decision:** Use fictional coalition, factions, places, symbols, and wars rather than directly modeling a current conflict.  
**Reason:** This preserves the intended geopolitical pressure and modern tone without tying play to real casualties or requiring legal/political claims.

### D-017: Drone Commander Names Replace Legacy Story Engine Names

**Decision:** New database name is `drone_commander`; new API uses sessions, prep, battles, units, opposition, directives, and events. Legacy adventure, monster, party, Moosehearth, and celebration-song names are migration-only.  
**Reason:** Copying inherited names into new contracts would create permanent conceptual debt and implementation mistakes.

### D-018: Pointy-Top Axial Grid

**Decision:** Logic uses a 50 by 50 pointy-top axial grid. Frontend applies fixed vertical compression for 2.5D presentation.  
**Reason:** Axial coordinates give reliable distance, neighbors, LOS, and pathfinding while keeping visual projection separate.

### D-019: One-Hex Single-Model Footprints In MVP

**Decision:** Small, medium, and large single-model units all occupy one logical hex; art and base markers show size.  
**Reason:** Multi-hex facing and rotation would substantially expand pathing, deployment, targeting, and animation scope. The fixed camera and clear base markers preserve visual scale.

### D-020: Directives Do Not Consume Actions

**Decision:** Directives may be edited during commander activation and lock at its end, but do not consume actions.  
**Reason:** Directives express intent rather than guarantee mechanical benefit. Charging an action for each order would punish the game's core command fantasy and crowd out RAM abilities.

### D-021: AOE Uses Hex Radius And Friendly Fire

**Decision:** `AOE N` includes every hex within axial distance N from a successful impact. Damage rolls separately per affected model; friendly fire applies. MVP misses do not scatter.  
**Reason:** The source uses AOE values without geometry, scatter, or friendly-fire rules. Hex radius is deterministic and previewable.

### D-022: Squad Attacks Resolve Per Living Model

**Decision:** A squad spends one Standard action and each living model with a legal target makes one attack.  
**Reason:** The source shows multiple individual soldiers with individual HP and says they can attack different targets. Batch resolution preserves that meaning while one agent controls the unit.

### D-023: Opposition Builds To Selected Cap

**Decision:** Opposition uses the selected cap even when the player leaves points unspent. It uses role-aware deterministic candidate scoring rather than hard counter-picking.  
**Reason:** This matches the source and makes point choice meaningful, while warning the player prevents surprise.

### D-024: Heavy Drone Speed Adjustment

**Decision:** Blocker Speed is 6 and Commander Support Speed is 8 rather than both being 10.  
**Reason:** Source values made heavily armored large platforms as fast as the smallest flying drones and contradicted their listed roles. These remain tuning values and can be restored after playtesting.

### D-025: Anti-Armor And Missing Weapon Details

**Decision:** Direct Attack range is 8. Anti-Armor has a range-12 Damage +10 missile with two shots plus its source heavy rifle.  
**Reason:** The source omitted Direct Attack range and gave Anti-Armor no anti-armor profile. Implementation cannot defer those basic legality/data fields.

### D-026: Production Assets Are Provider-Neutral

**Decision:** ChatGPT/image generation, ElevenLabs, and Suno may create assets, but runtime code uses manifests/adapters and records approval/license status.  
**Reason:** Production must survive provider changes and distinguish generated drafts from approved, legally usable assets.

### D-027: Desktop Is Primary, Smaller Screens Remain Functional

**Decision:** Optimize battle play for desktop, support tablet layouts fully, and provide a stacked functional phone layout.  
**Reason:** A 50 by 50 command battlefield is naturally desktop-heavy, but the source explicitly requires responsiveness and essential access cannot disappear.

## 2. Working Assumptions

These assumptions unblock implementation but should be checked against the real repository:

- The project is a fork or successor of Story Engine and may contain reusable session, event, provider, feedback, Docker, and audio code.
- React 18, Vite, FastAPI, PostgreSQL, Docker Compose, and PixiJS remain desired technologies.
- There is no required account system for local VS/MVP development.
- Public hosting may be anonymous initially, so production session access must not trust UUID secrecy.
- Placeholder assets are acceptable until gameplay contracts are stable.
- The user can choose all army content available at the current release gate; campaign unlocks apply only inside Campaign.
- Full fog of war and elevation are deferred.
- Exact balance will be determined by simulation and playtesting, not prose alone.

## 3. Product Decisions Reserved For Raymond

These do not block VS architecture; ask when the relevant gate begins.

1. Final product title and fictional coalition/faction names.
2. Final visual art style: painted 2D, realistic render, stylized tactical miniatures, or another direction.
3. Commander avatar roster, names, voice identities, and whether players may name their commander.
4. Preferred production model, image, TTS, sound-effect, and music providers plus spending limits.
5. Whether the first hosted release is private, public anonymous, or account-based.
6. Desired violence/gore ceiling and age-rating target.
7. Campaign story, characters, briefing tone, and final mission names.
8. Whether assisted/veteran difficulty ships with Campaign or after it.
9. Whether future faction asymmetry changes stats or remains cosmetic/doctrine-only.
10. Whether manual deployment, multiplayer, or strategic progression is the first post-campaign expansion.

## 4. Tuning Questions Resolved By Testing

Do not block implementation on these. Store them as content/config values and report evidence:

- unit point costs and heavy-drone speeds
- weapon range/damage and AOE size
- cover bonuses
- RAM costs and ability durations
- signal radius and relay range
- ammunition/charge counts
- opposition role weights
- objective score/round limits
- agent menu size, timeout, prefetch depth, and radio length
- animation speed, zoom limits, and performance targets
- campaign force handicaps and doctrine weights
