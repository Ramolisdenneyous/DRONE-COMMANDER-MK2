"""Generate female commander VO clips via ElevenLabs text-to-speech."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT.parent / "AI API Tools" / "api_keys" / ".env"
JOBS_PATH = ROOT / "sfx_commander_female_vo.json"
OUT_DIR = ROOT / "frontend" / "public" / "assets" / "sfx"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def synthesize(api_key: str, voice_id: str, text: str, model_id: str) -> bytes:
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.38,
            "similarity_boost": 0.82,
            "style": 0.62,
            "use_speaker_boost": True,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            data=body,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read()
        except (urllib.error.HTTPError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if isinstance(exc, urllib.error.HTTPError):
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"ElevenLabs TTS failed: HTTP {exc.code}\n{detail}")
            print(f"  attempt {attempt + 1} failed, retrying...")
    raise RuntimeError(str(last_error))


def main() -> None:
    env = load_env(ENV_PATH)
    api_key = env.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise RuntimeError(f"Missing ELEVENLABS_API_KEY in {ENV_PATH}")

    spec = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    voice_id = spec["voice_id"]
    model_id = spec.get("model_id", "eleven_multilingual_v2")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for job in spec["jobs"]:
        name = re.sub(r"[^a-zA-Z0-9._-]+", "-", job["name"]).strip("-")
        out_path = OUT_DIR / f"{name}.mp3"
        if out_path.exists() and out_path.stat().st_size > 1000:
            print(f"Skipping existing {out_path.name}")
            continue
        print(f"Generating {out_path.name} ...")
        audio = synthesize(api_key, voice_id, job["text"], model_id)
        out_path.write_bytes(audio)
        print(f"  saved {len(audio)} bytes")

    print(f"Done. {len(spec['jobs'])} files in {OUT_DIR}")


if __name__ == "__main__":
    main()
