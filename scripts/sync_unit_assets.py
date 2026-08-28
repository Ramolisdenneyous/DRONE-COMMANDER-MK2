"""Copy Wargame Raw Images into frontend/public/assets/units with normalized names."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT.parent / "Wargame Raw Images"
OUT = ROOT / "frontend" / "public" / "assets" / "units"


def ensure_dir(name: str) -> Path:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def cp(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    shutil.copy2(src, dst)


def sample_frames(src_dir: Path, glob: str, out_dir: Path, prefix: str, max_frames: int = 8) -> list[str]:
    files = sorted(src_dir.glob(glob))
    files = [f for f in files if f.is_file() and "sprite-max-px" not in str(f)]
    if not files:
        return []
    if len(files) <= max_frames:
        picked = files
    else:
        step = len(files) / max_frames
        picked = [files[int(i * step)] for i in range(max_frames)]
    names: list[str] = []
    for i, src in enumerate(picked, start=1):
        name = f"{prefix}{i}.png"
        cp(src, out_dir / name)
        names.append(name)
    return names


def main() -> None:
    if not RAW.is_dir():
        raise SystemExit(f"Missing raw art folder: {RAW}")

    # --- blue infantryman ---
    d = ensure_dir("blue-infantryman")
    src_inf = RAW / "Blue-Infantryman"
    for src_name, dst_name in [
        ("blue-Infentryman-walk1.png", "walk1.png"),
        ("blue-Infentryman-walk1.5.png", "walk1_5.png"),
        ("blue-Infentryman-walk2.png", "walk2.png"),
        ("blue-Infentryman-walk2.5.png", "walk2_5.png"),
        ("blue-Infentryman-walk3.png", "walk3.png"),
        ("blue-Infentryman-walk4.png", "walk4.png"),
        ("blue-Infentryman-walk4.5.png", "walk4_5.png"),
        ("blue-Infentryman-walk5.png", "walk5.png"),
        ("blue-Infentryman-walk5.5.png", "walk5_5.png"),
        ("blue-Infentryman-walk6.png", "walk6.png"),
    ]:
        cp(src_inf / src_name, d / dst_name)
    for i in range(1, 5):
        cp(src_inf / "Shooting" / f"Blue-Fire{i}.png", d / f"shoot{i}.png")
    cp(d / "walk1.png", d / "ready.png")

    # --- blue ranger ---
    d = ensure_dir("blue-ranger")
    src = RAW / "Blue Ranger"
    cp(src / "Blue-Ranger-Ready.png", d / "ready.png")
    sample_frames(src / "Running left", "frame_*.png", d, "walk", max_frames=8)
    sample_frames(src / "Shooting Left", "frame_*.png", d, "shoot", max_frames=4)

    # --- blue engineer ---
    d = ensure_dir("blue-engineer")
    src = RAW / "Blue Engeneer"
    cp(src / "Blue Engeneer Ready.png", d / "ready.png")
    sample_frames(src / "Walking Right", "frame_*.png", d, "walk", max_frames=8)
    sample_frames(src / "Shooting right", "frame_*.png", d, "shoot", max_frames=4)
    sample_frames(src / "Set mine-or-charge", "frame_*.png", d, "deploy", max_frames=8)

    # --- blue one-way drone ---
    d = ensure_dir("blue-one-way-drone")
    src = RAW / "Blue One Way Attack Drone"
    cp(src / "Drone1A-Ready1.png", d / "ready.png")
    fly_src = src / "Flying Left"
    for i in range(1, 5):
        cp(fly_src / f"Drone1A-flying{i}.png", d / f"fly{i}.png")

    # --- blue direct attack drone ---
    d = ensure_dir("blue-direct-attack-drone")
    src = RAW / "Blue Direct Attack Drone"
    cp(src / "Drone1B-ready.png", d / "ready.png")
    cp(src / "Drone1B-ready-and-empty.png", d / "empty.png")
    armed = src / "Flying left-armed"
    for i in range(1, 5):
        cp(armed / f"Drone1B-fly{i}.png", d / f"fly{i}.png")
    empty = src / "Flying Left-empty"
    for i in range(1, 5):
        cp(empty / f"Drone1B-fly{i}-empty.png", d / f"fly{i}-empty.png")

    # --- blue flanker drone ---
    d = ensure_dir("blue-flanker-drone")
    src = RAW / "Blue Flanker Drone"
    cp(src / "Blue Drone Ready.png", d / "ready.png")
    sample_frames(src / "Rolling Left", "frame_*.png", d, "roll", max_frames=4)
    sample_frames(src / "Shooting Left", "frame_*.png", d, "shoot", max_frames=4)

    # --- blue anti-armor + commander support (large drones) ---
    for folder, raw_name, ready_file in [
        ("blue-anti-armor-drone", "Blue Anti Armor Drone", "Large Blue Drone ready.png"),
        ("blue-commander-support-drone", "Blue Commander Support Drone", "Commander Support Drone Ready.png"),
    ]:
        d = ensure_dir(folder)
        src = RAW / raw_name
        cp(src / ready_file, d / "ready.png")
        move_dir = next(p for p in src.iterdir() if p.is_dir() and p.name.lower().startswith(("walking", "moving")))
        shoot_dir = next(p for p in src.iterdir() if p.is_dir() and p.name.lower().startswith("shooting"))
        sample_frames(move_dir, "frame_*.png", d, "roll", max_frames=4)
        sample_frames(shoot_dir, "frame_*.png", d, "shoot", max_frames=4)

    # --- red infantryman ---
    d = ensure_dir("red-infantryman")
    src = RAW / "Red-Infantryman"
    cp(src / "Red-Ready1.png", d / "ready.png")
    for i in range(1, 7):
        cp(src / f"Red-walk{i}.png", d / f"walk{i}.png")
    for i in range(1, 5):
        cp(src / "Shooting" / f"Red-fire{i}.png", d / f"shoot{i}.png")

    # --- red ranger ---
    d = ensure_dir("red-ranger")
    src = RAW / "Red Ranger"
    cp(src / "Red-Ranger-Ready.png", d / "ready.png")
    run_src = src / "Running Left"
    for i in range(1, 10):
        cp(run_src / f"runing{i}.png", d / f"walk{i}.png")
    sample_frames(src / "Shooting Right", "frame_*.png", d, "shoot", max_frames=4)

    # --- red engineer ---
    d = ensure_dir("red-engineer")
    src = RAW / "Red Engeneer"
    cp(src / "Red Engeneer ready.png", d / "ready.png")
    walk_dir = next(p for p in src.iterdir() if p.is_dir() and "Walking" in p.name)
    shoot_dir = next(p for p in src.iterdir() if p.is_dir() and "Shooting" in p.name)
    sample_frames(walk_dir, "frame_*.png", d, "walk", max_frames=8)
    sample_frames(shoot_dir, "frame_*.png", d, "shoot", max_frames=4)
    sample_frames(src / "Deploy Mine", "frame_*.png", d, "deploy", max_frames=8)

    # --- red one-way dog ---
    d = ensure_dir("red-one-way-dog")
    src = RAW / "Red One Way Dog Drone"
    cp(src / "Red-DOG-ready.png", d / "ready.png")
    run_src = src / "run Left"
    for i in range(1, 5):
        cp(run_src / f"Red-DOG-run{i}.png", d / f"run{i}.png")

    # --- red direct attack dog ---
    d = ensure_dir("red-direct-attack-dog")
    src = RAW / "Red Direct Attack Dog Drone"
    cp(src / "Red-DOG-ready.png", d / "ready.png")
    run_src = src / "run Left"
    for i in range(1, 5):
        cp(run_src / f"Red-DOG-run{i}.png", d / f"run{i}.png")
    shoot_src = src / "shoot left"
    for i in range(1, 4):
        cp(shoot_src / f"Red-DOG-shoot{i}.png", d / f"shoot{i}.png")

    # --- red tank ---
    d = ensure_dir("red-tank")
    src = RAW / "Red Tank"
    cp(src / "Red-tank-ready.png", d / "ready.png")
    roll_src = src / "Rolling left"
    for i in range(1, 4):
        cp(roll_src / f"Red-tank-rolling{i}.png", d / f"roll{i}.png")
    sample_frames(src / "Shooting left", "frame_*.png", d, "shoot", max_frames=4)

    # Legacy alias folders (old MK1 paths still referenced in older builds)
    alias_pairs = [
        ("blue-infantryman", "blue-infantry"),
        ("red-infantryman", "red-infantry"),
        ("blue-one-way-drone", "blue-drone-1a"),
        ("blue-direct-attack-drone", "blue-drone-1b"),
        ("blue-flanker-drone", "blue-drone-2a"),
        ("red-direct-attack-dog", "red-dog"),
    ]
    for src_name, dst_name in alias_pairs:
        src_d = OUT / src_name
        dst_d = OUT / dst_name
        if dst_d.exists():
            shutil.rmtree(dst_d)
        shutil.copytree(src_d, dst_d)

    print(f"Synced unit art into {OUT}")


if __name__ == "__main__":
    main()
