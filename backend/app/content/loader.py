"""Content catalog loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from ..config import settings


class WeaponDef(BaseModel):
    id: str
    display_name: str
    range: int
    damage: int
    area: int = 0
    ammo: int | None = None  # None = unlimited
    tags: list[str] = Field(default_factory=list)


class AbilityDef(BaseModel):
    id: str
    display_name: str
    action_cost: str  # standard|move|minor|none
    ram_cost: int = 0
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    once_per_battle: bool = False
    area: int = 0
    damage: int | None = None
    range: int | None = None
    passive: bool = False


class UnitDef(BaseModel):
    id: str
    display_name: str
    side_availability: list[str]
    category: str
    size_class: str
    roles: list[str] = Field(default_factory=list)
    point_cost: int
    model_count: int = 1
    speed: int
    attack: int = 0
    defense: int
    armor: int
    hp_per_model: int
    weapons: list[str] = Field(default_factory=list)
    abilities: list[str] = Field(default_factory=list)
    movement_traits: list[str] = Field(default_factory=lambda: ["ground"])
    capacity: int = 0
    max_per_army: int | None = None
    wreckage_terrain_id: str | None = None
    agent_profile_id: str = "default"
    asset_set_id: str
    content_version: str = "vs-0.1.0"


class LoadoutDef(BaseModel):
    id: str
    display_name: str
    attack: int = 0
    defense: int = 10
    armor: int = 11
    speed: int = 6
    hp: int = 5
    ram_capacity: int = 6
    weapons: list[str] = Field(default_factory=list)
    allowed_abilities: list[str] = Field(default_factory=list)
    passive: str = ""


class TerrainDef(BaseModel):
    id: str
    display_name: str
    ground_move_cost: int | None = 1  # None = blocked
    fly_move_cost: int | None = 1
    cover: str = "none"
    blocks_los: bool = False
    solid_occupancy: bool = True
    tags: list[str] = Field(default_factory=list)


class MapDef(BaseModel):
    id: str
    display_name: str
    width: int = 50
    height: int = 50
    ground_asset: str
    select_asset: str | None = None
    terrain: list[dict[str, Any]] = Field(default_factory=list)
    friendly_deploy_rows: list[int] = Field(default_factory=lambda: [45, 46, 47, 48, 49])
    opposition_deploy_rows: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])


class MissionDef(BaseModel):
    id: str
    display_name: str
    point_cap: int = 15
    objective_type: str = "annihilation"
    map_id: str
    mode: str = "freestyle_vs"


class FactionDef(BaseModel):
    id: str
    display_name: str
    side: str
    doctrine_profile_id: str = "balanced"


class ArmyOrderDef(BaseModel):
    id: str
    label: str
    raw_text: str = ""
    tags: list[str] = Field(default_factory=list)
    voice_line: str | None = None
    requires_target: bool = False


class ContentCatalog(BaseModel):
    content_version: str
    units: dict[str, UnitDef]
    weapons: dict[str, WeaponDef]
    abilities: dict[str, AbilityDef]
    loadouts: dict[str, LoadoutDef]
    terrain: dict[str, TerrainDef]
    maps: dict[str, MapDef]
    missions: dict[str, MissionDef]
    factions: dict[str, FactionDef]
    opposition_map: dict[str, str]
    army_orders: dict[str, ArmyOrderDef] = Field(default_factory=dict)
    asset_manifest: dict[str, Any] = Field(default_factory=dict)


_catalog: ContentCatalog | None = None


def content_root() -> Path:
    env = Path(settings.content_root)
    if env.is_absolute() and env.exists():
        return env
    here = Path(__file__).resolve()
    # backend/app/content/loader.py -> repo root is parents[3]
    candidates = [
        Path.cwd() / env,
        Path.cwd().parent / env,
        here.parents[3] / "content",
        here.parents[2] / "content",
        Path("/app/content"),
        env,
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[2]


def _load_yaml_dir(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not path.exists():
        return items
    for file in sorted(path.glob("*.yaml")):
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
        if data is None:
            continue
        if isinstance(data, list):
            items.extend(data)
        else:
            items.append(data)
    return items


def load_catalog(force: bool = False) -> ContentCatalog:
    global _catalog
    if _catalog is not None and not force:
        return _catalog

    root = content_root()
    errors: list[str] = []

    try:
        weapons = {w["id"]: WeaponDef.model_validate(w) for w in _load_yaml_dir(root / "weapons")}
        abilities = {a["id"]: AbilityDef.model_validate(a) for a in _load_yaml_dir(root / "abilities")}
        units = {u["id"]: UnitDef.model_validate(u) for u in _load_yaml_dir(root / "units")}
        loadouts = {l["id"]: LoadoutDef.model_validate(l) for l in _load_yaml_dir(root / "loadouts")}
        terrain = {t["id"]: TerrainDef.model_validate(t) for t in _load_yaml_dir(root / "terrain")}
        maps = {m["id"]: MapDef.model_validate(m) for m in _load_yaml_dir(root / "maps")}
        missions = {m["id"]: MissionDef.model_validate(m) for m in _load_yaml_dir(root / "missions")}
        factions = {}
        for f in _load_yaml_dir(root / "factions"):
            if isinstance(f, dict) and "id" in f and "side" in f:
                factions[f["id"]] = FactionDef.model_validate(f)

        opp_file = root / "factions" / "opposition_map.yaml"
        opposition_map = {}
        if opp_file.exists():
            opposition_map = yaml.safe_load(opp_file.read_text(encoding="utf-8")) or {}

        army_orders = {
            o["id"]: ArmyOrderDef.model_validate(o) for o in _load_yaml_dir(root / "orders") if isinstance(o, dict) and "id" in o
        }

        asset_file = root / "assets" / "manifest.yaml"
        asset_manifest = {}
        if asset_file.exists():
            asset_manifest = yaml.safe_load(asset_file.read_text(encoding="utf-8")) or {}

        # Cross-reference validation
        for uid, unit in units.items():
            for wid in unit.weapons:
                if wid not in weapons:
                    errors.append(f"units.{uid}.weapons: unknown weapon '{wid}'")
            for aid in unit.abilities:
                if aid not in abilities:
                    errors.append(f"units.{uid}.abilities: unknown ability '{aid}'")
        for lid, loadout in loadouts.items():
            for wid in loadout.weapons:
                if wid not in weapons:
                    errors.append(f"loadouts.{lid}.weapons: unknown weapon '{wid}'")
            for aid in loadout.allowed_abilities:
                if aid not in abilities:
                    errors.append(f"loadouts.{lid}.allowed_abilities: unknown ability '{aid}'")
        for mid, mission in missions.items():
            if mission.map_id not in maps:
                errors.append(f"missions.{mid}.map_id: unknown map '{mission.map_id}'")

        if errors:
            raise ValueError("Content validation failed:\n" + "\n".join(errors))

        _catalog = ContentCatalog(
            content_version=settings.content_version,
            units=units,
            weapons=weapons,
            abilities=abilities,
            loadouts=loadouts,
            terrain=terrain,
            maps=maps,
            missions=missions,
            factions=factions,
            opposition_map=opposition_map,
            army_orders=army_orders,
            asset_manifest=asset_manifest,
        )
        return _catalog
    except ValidationError as exc:
        raise ValueError(f"Content schema validation failed: {exc}") from exc


def get_catalog() -> ContentCatalog:
    return load_catalog()
