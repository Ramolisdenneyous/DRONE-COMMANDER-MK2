export type UnitSpriteSet = {
  folder: string;
  artFace: 1 | -1;
  /** Battlefield size vs default hex fit. 1 = current default; 2 = twice as large; 0.5 = half. */
  mapScale?: number;
  ready: string;
  readyEmpty?: string;
  walk?: string[];
  fly?: string[];
  flyEmpty?: string[];
  roll?: string[];
  run?: string[];
  shoot?: string[];
  deploy?: string[];
};

function unitAssetUrl(folder: string, file: string): string {
  return `/assets/units/${folder}/${file}`;
}

/** asset_set_id → sprite manifest (mirrors content/assets/unit_sprites.yaml) */
export const UNIT_SPRITES: Record<string, UnitSpriteSet> = {
  blue_infantry: {
    folder: "blue-infantryman",
    artFace: 1,
    ready: "ready.png",
    walk: [
      "walk1.png",
      "walk1_5.png",
      "walk2.png",
      "walk2_5.png",
      "walk3.png",
      "walk4.png",
      "walk4_5.png",
      "walk5.png",
      "walk5_5.png",
      "walk6.png",
    ],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  friendly_ranger_squad: {
    folder: "blue-ranger",
    // Source walk/shoot art faces left ("Running left" / "Shooting Left")
    artFace: -1,
    ready: "ready.png",
    walk: ["walk1.png", "walk2.png", "walk3.png", "walk4.png", "walk5.png", "walk6.png", "walk7.png", "walk8.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  friendly_combat_engineers: {
    folder: "blue-engineer",
    artFace: 1,
    ready: "ready.png",
    walk: ["walk1.png", "walk2.png", "walk3.png", "walk4.png", "walk5.png", "walk6.png", "walk7.png", "walk8.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
    deploy: ["deploy1.png", "deploy2.png", "deploy3.png", "deploy4.png", "deploy5.png", "deploy6.png", "deploy7.png", "deploy8.png"],
  },
  blue_drone_1a: {
    folder: "blue-one-way-drone",
    artFace: -1, // Flying Left
    mapScale: 0.5,
    ready: "ready.png",
    fly: ["fly1.png", "fly2.png", "fly3.png", "fly4.png"],
  },
  blue_drone_1b: {
    folder: "blue-direct-attack-drone",
    artFace: -1, // Flying left-armed / empty
    mapScale: 0.5,
    ready: "ready.png",
    readyEmpty: "empty.png",
    fly: ["fly1.png", "fly2.png", "fly3.png", "fly4.png"],
    flyEmpty: ["fly1-empty.png", "fly2-empty.png", "fly3-empty.png", "fly4-empty.png"],
  },
  blue_drone_2a: {
    folder: "blue-flanker-drone",
    artFace: -1, // Rolling Left / Shooting Left
    mapScale: 0.5,
    ready: "ready.png",
    roll: ["roll1.png", "roll2.png", "roll3.png", "roll4.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  friendly_commander_support_drone: {
    folder: "blue-commander-support-drone",
    artFace: -1, // Moving Left / Shooting Left
    mapScale: 2,
    ready: "ready.png",
    roll: ["roll1.png", "roll2.png", "roll3.png", "roll4.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  friendly_anti_armor_drone: {
    folder: "blue-anti-armor-drone",
    artFace: -1, // Walking Left / Shooting Left
    mapScale: 2,
    ready: "ready.png",
    roll: ["roll1.png", "roll2.png", "roll3.png", "roll4.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  red_infantry: {
    folder: "red-infantryman",
    artFace: -1,
    ready: "ready.png",
    walk: ["walk1.png", "walk2.png", "walk3.png", "walk4.png", "walk5.png", "walk6.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  opposition_ranger_squad: {
    folder: "red-ranger",
    // Run frames face right despite "Running Left" folder name; shoot is "Shooting Right"
    artFace: 1,
    ready: "ready.png",
    walk: ["walk1.png", "walk2.png", "walk3.png", "walk4.png", "walk5.png", "walk6.png", "walk7.png", "walk8.png", "walk9.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  opposition_combat_engineers: {
    folder: "red-engineer",
    artFace: 1, // Walking Right / Shooting to the right
    ready: "ready.png",
    walk: ["walk1.png", "walk2.png", "walk3.png", "walk4.png", "walk5.png", "walk6.png", "walk7.png", "walk8.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
    deploy: ["deploy1.png", "deploy2.png", "deploy3.png", "deploy4.png", "deploy5.png", "deploy6.png", "deploy7.png", "deploy8.png"],
  },
  red_dog: {
    folder: "red-direct-attack-dog",
    artFace: -1,
    mapScale: 0.5,
    ready: "ready.png",
    run: ["run1.png", "run2.png", "run3.png", "run4.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png"],
  },
  opposition_impact_drone: {
    folder: "red-one-way-dog",
    artFace: -1,
    mapScale: 0.5,
    ready: "ready.png",
    run: ["run1.png", "run2.png", "run3.png", "run4.png"],
  },
  red_tank: {
    folder: "red-tank",
    artFace: -1,
    ready: "ready.png",
    roll: ["roll1.png", "roll2.png", "roll3.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
  red_commander: {
    folder: "red-commander",
    artFace: -1,
    mapScale: 1.5,
    ready: "ready.png",
    roll: ["roll1.png", "roll2.png", "roll3.png", "roll4.png"],
    shoot: ["shoot1.png", "shoot2.png", "shoot3.png", "shoot4.png"],
  },
};

/** Authoritative art lookup — definition_id beats stale asset_set_id from older deploys. */
export const DEFINITION_TO_ASSET_SET: Record<string, string> = {
  friendly_commander: "commander",
  friendly_infantry_squad: "blue_infantry",
  friendly_ranger_squad: "friendly_ranger_squad",
  friendly_combat_engineers: "friendly_combat_engineers",
  friendly_one_way_drone: "blue_drone_1a",
  friendly_direct_attack_drone: "blue_drone_1b",
  friendly_flanker_drone: "blue_drone_2a",
  friendly_commander_support_drone: "friendly_commander_support_drone",
  friendly_anti_armor_drone: "friendly_anti_armor_drone",
  opposition_line_cell: "red_infantry",
  opposition_ranger_squad: "opposition_ranger_squad",
  opposition_combat_engineers: "opposition_combat_engineers",
  opposition_impact_drone: "opposition_impact_drone",
  opposition_burst_drone: "red_dog",
  opposition_tank: "red_tank",
  opposition_commander: "red_commander",
};

export type UnitSpriteLookup = {
  asset_set_id?: string;
  definition_id?: string;
  category?: string;
  side?: string;
  ammo?: Record<string, number>;
};

export function resolveAssetSetId(
  assetSetId?: string,
  category?: string,
  side?: string,
  definitionId?: string,
): string {
  if (category === "commander") {
    if (definitionId === "opposition_commander" || side === "opposition") return "red_commander";
    return "commander";
  }
  if (definitionId && DEFINITION_TO_ASSET_SET[definitionId]) {
    return DEFINITION_TO_ASSET_SET[definitionId];
  }
  if (assetSetId && UNIT_SPRITES[assetSetId]) return assetSetId;
  if (category === "soldier_squad") return side === "opposition" ? "red_infantry" : "blue_infantry";
  return assetSetId || "blue_infantry";
}

export function unitArtFace(
  assetSetId?: string,
  category?: string,
  commanderAvatar?: string,
  definitionId?: string,
): 1 | -1 {
  if (category === "commander" || assetSetId === "commander" || assetSetId === "red_commander") {
    if (definitionId === "opposition_commander") return -1;
    return commanderAvatar === "female" ? 1 : -1;
  }
  const id = resolveAssetSetId(assetSetId, category, undefined, definitionId);
  const set = UNIT_SPRITES[id];
  return set?.artFace ?? 1;
}

/** Per-unit battlefield size multiplier (default 1). */
export function unitMapScale(
  assetSetId?: string,
  category?: string,
  side?: string,
  definitionId?: string,
): number {
  const id = resolveAssetSetId(assetSetId, category, side, definitionId);
  const set = UNIT_SPRITES[id];
  const s = set?.mapScale;
  return typeof s === "number" && s > 0 ? s : 1;
}

/**
 * Target on-map sprite height in px for a given hex radius R.
 * Infantry/commander stay at the tuned defaults; mapScale adjusts drones etc.
 */
export function unitSpriteTargetHeight(
  hexR: number,
  opts: {
    category?: string;
    sizeClass?: string;
    assetSetId?: string;
    side?: string;
    definitionId?: string;
  },
): number {
  const { category, sizeClass } = opts;
  let h: number;
  if (category === "commander") h = hexR * 2.1;
  else if (category === "soldier_squad") h = hexR * 1.85;
  else if (sizeClass === "large" || category === "drone") h = hexR * 1.7;
  else h = hexR * 1.9;
  return h * unitMapScale(opts.assetSetId, category, opts.side, opts.definitionId);
}

function spriteSet(unit: UnitSpriteLookup): UnitSpriteSet | undefined {
  const id = resolveAssetSetId(unit.asset_set_id, unit.category, unit.side, unit.definition_id);
  return UNIT_SPRITES[id];
}

export function unitReadyUrl(unit: UnitSpriteLookup, avatar?: string): string {
  if (unit.category === "commander") {
    if (unit.definition_id === "opposition_commander" || unit.side === "opposition") {
      return unitAssetUrl("red-commander", "ready.png");
    }
    return avatar === "female"
      ? "/assets/avatars/Drone-commander-Female.png"
      : "/assets/avatars/Drone-commander-Male.png";
  }
  const set = spriteSet(unit);
  if (!set) return unitAssetUrl("blue-infantryman", "walk1.png");
  const resolved = resolveAssetSetId(unit.asset_set_id, unit.category, unit.side, unit.definition_id);
  const empty =
    resolved === "blue_drone_1b" &&
    unit.ammo &&
    Object.values(unit.ammo).some((n) => Number(n) <= 0) &&
    set.readyEmpty;
  const file = empty ? set.readyEmpty! : set.ready;
  return unitAssetUrl(set.folder, file);
}

export function unitAmmoEmpty(u: { ammo?: Record<string, number> }): boolean {
  const ammo = u?.ammo;
  if (!ammo || typeof ammo !== "object") return false;
  return Object.values(ammo).some((n) => Number(n) <= 0);
}

export function moveFrameUrls(
  assetSetId?: string,
  category?: string,
  side?: string,
  commanderAvatar?: string,
  ammoEmpty?: boolean,
  definitionId?: string,
): string[] {
  if (category === "commander" || assetSetId === "commander") {
    if (definitionId === "opposition_commander" || side === "opposition") {
      const unit: UnitSpriteLookup = { asset_set_id: "red_commander", category, side, definition_id: definitionId };
      const set = spriteSet(unit);
      const frames = set?.roll || set?.run || set?.walk;
      if (frames?.length) return frames.map((f) => unitAssetUrl(set!.folder, f));
    }
    const gender = commanderAvatar === "female" ? "Female" : "Male";
    return Array.from({ length: 9 }, (_, i) => `/assets/avatars/Drone-commander-${gender}-walk${i + 1}.png`);
  }
  const unit: UnitSpriteLookup = { asset_set_id: assetSetId, category, side, definition_id: definitionId };
  const set = spriteSet(unit);
  if (!set) return [];
  const resolved = resolveAssetSetId(assetSetId, category, side, definitionId);
  if (resolved === "blue_drone_1b" && ammoEmpty) {
    if (set.flyEmpty?.length) return set.flyEmpty.map((f) => unitAssetUrl(set.folder, f));
    if (set.readyEmpty) return [unitAssetUrl(set.folder, set.readyEmpty)];
  }
  const frames = set.fly || set.roll || set.run || set.walk;
  if (!frames?.length) return [];
  return frames.map((f) => unitAssetUrl(set.folder, f));
}

export function shootFrameUrls(
  assetSetId?: string,
  category?: string,
  side?: string,
  commanderAvatar?: string,
  definitionId?: string,
): string[] {
  if (category === "commander" || assetSetId === "commander") {
    if (definitionId === "opposition_commander" || side === "opposition") {
      const unit: UnitSpriteLookup = { asset_set_id: "red_commander", category, side, definition_id: definitionId };
      const set = spriteSet(unit);
      if (set?.shoot?.length) return set.shoot.map((f) => unitAssetUrl(set.folder, f));
    }
    const gender = commanderAvatar === "female" ? "Female" : "Male";
    return Array.from({ length: 9 }, (_, i) => `/assets/avatars/Drone-commander-${gender}-fire${i + 1}.png`);
  }
  const unit: UnitSpriteLookup = { asset_set_id: assetSetId, category, side, definition_id: definitionId };
  const set = spriteSet(unit);
  if (!set?.shoot?.length) return [];
  return set.shoot.map((f) => unitAssetUrl(set.folder, f));
}

export function deployFrameUrls(
  assetSetId?: string,
  category?: string,
  side?: string,
  definitionId?: string,
): string[] {
  const unit: UnitSpriteLookup = { asset_set_id: assetSetId, category, side, definition_id: definitionId };
  const set = spriteSet(unit);
  if (!set?.deploy?.length) return [];
  return set.deploy.map((f) => unitAssetUrl(set.folder, f));
}

export function unitPortraitUrl(unit: UnitSpriteLookup, avatar?: string): string {
  return unitReadyUrl(unit, avatar);
}
