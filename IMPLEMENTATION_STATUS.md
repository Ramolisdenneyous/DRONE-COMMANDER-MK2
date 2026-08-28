# Implementation Status — MK2

**Current gate:** Phase 2 kickoff — splash + match setup wired  
**Workspace:** `Drone-Commander-MK2` (ports 5179 / 8006 / 5438)

## Completed this session

- Copied MK1 POC into MK2 with side-by-side Docker ports
- Landing splash + logo assets under `frontend/public/assets/landing/`
- Four battlefield select cards + ground tiles under `frontend/public/assets/maps/`
- App flow: **Splash → Map + Point Cap → Army Builder → Battle → Debrief**
- Backend `prep.map_id` override + boot exposes `maps` and point caps 15–100
- Stub map defs for Northern Tundra, Open Fields, Urban Combat (reuse ME terrain layout until packs land)

## Inherited from MK1

- VS Gates 0–3 rules engine, Luna agents, Prep/Battle/Debrief, pytest suite

## Next

1. Dedicated terrain packs for Tundra / Fields / Urban
2. Gate 4 Freestyle roster + systems (smoke, mines, paint, transport…)
3. Mission/objective variety beyond temple control

## Local URLs (MK2)

- UI: http://localhost:5179
- API: http://localhost:8006/health
