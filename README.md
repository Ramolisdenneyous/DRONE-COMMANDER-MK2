# Drone Commander MK2

**Phase 2 workspace** — Freestyle MVP content and flow, forked from the MK1 proof-of-concept.

MK1 remains the frozen GitHub POC snapshot: [DRONE-COMMANDER-MK1](https://github.com/Ramolisdenneyous/DRONE-COMMANDER-MK1)

## Phase 2 direction (planned)

1. **Splash / landing** — game identity image and entry
2. **Match setup** — choose map and point cap
3. **Army building** — current MK1 Mission Prep (start of the old flow)
4. Then deploy → battle → debrief as today

Plus Gate 4 Freestyle content: fuller roster, 15–100 point caps, control/extraction objectives, richer maps/systems.

## Stack (MK2 ports — side-by-side with MK1)

| Service | MK2 port | MK1 port |
|---------|----------|----------|
| Postgres (`drone_commander_mk2`) | **5438** | 5436 |
| Backend FastAPI | **8006** | 8004 |
| Frontend Vite/React/PixiJS | **5179** | 5177 |

## Quick start

```bash
cd "C:\Users\Raymond\Desktop\Test File\hello.js\Drone-Commander-MK2"
# .env already present locally from MK1 copy — or: cp .env.example .env

docker compose up --build
```

- UI: http://localhost:5179
- API health: http://localhost:8006/health

Hard-refresh (`Ctrl+Shift+R`) after frontend rebuilds.

## Inherited from MK1 POC

- Backend-authoritative hex rules engine
- Live OpenAI `gpt-5.6-luna` unit agents + deterministic fallback
- Mission Prep / Battle / Debrief
- Content YAML catalogs, Pixi battlefield, SFX/music assets
- pytest suite under `backend/tests/`

See [IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md) for gate status.

## License

[MIT License](./LICENSE) — Copyright (c) 2026 Ramolisdenneyous.
