export type TerrainPack = "middle-east" | "northern-tundra" | "open-fields" | "urban-combat";

export function terrainPackForMap(mapId?: string | null): TerrainPack {
  const id = mapId || "";
  if (id.includes("tundra")) return "northern-tundra";
  if (id.includes("open_fields")) return "open-fields";
  if (id.includes("urban")) return "urban-combat";
  return "middle-east";
}

const me = (file: string) => `/assets/battlefield/terrain/${file}`;
const pk = (pack: TerrainPack, file: string) => `/assets/battlefield/terrain/${pack}/${file}`;

export const TERRAIN_SPRITES_BY_PACK: Record<TerrainPack, Record<string, string[]>> = {
  "middle-east": {
    wall: [me("Terrain-Walls1.png")],
    building: [
      me("Terrain-building1.png"),
      me("Terrain-building2.png"),
      me("Terrain-Building-damaged.png"),
      me("Terrain-Temple.png"),
    ],
    rubble: [
      me("Terrain-rock-obstuction1.png"),
      me("Terrain-rock-obstuction2.png"),
      me("Terrain-rock-obstuction3.png"),
      me("Terrain-rock-obstuction4.png"),
    ],
    crater: [me("Terrain-gental-hill.png")],
    wreckage: [me("Terrain-rocky-hill.png"), me("Terrain-steep-hill.png")],
    trees: [me("Terrain-trees1.png")],
    road: [],
    clear: [],
  },
  "northern-tundra": {
    wall: [pk("northern-tundra", "trench.png"), pk("northern-tundra", "trench2.png")],
    building: [
      pk("northern-tundra", "bunker.png"),
      pk("northern-tundra", "cabin1.png"),
      pk("northern-tundra", "cabin2.png"),
      pk("northern-tundra", "comms-building.png"),
      pk("northern-tundra", "outpost1.png"),
      pk("northern-tundra", "outpost2.png"),
      pk("northern-tundra", "spire1.png"),
      pk("northern-tundra", "spire2.png"),
    ],
    rubble: [
      pk("northern-tundra", "rocks1.png"),
      pk("northern-tundra", "rocks2.png"),
      pk("northern-tundra", "rocks3.png"),
      pk("northern-tundra", "rocks4.png"),
    ],
    crater: [
      pk("northern-tundra", "hill1.png"),
      pk("northern-tundra", "hill2.png"),
      pk("northern-tundra", "hill3.png"),
      pk("northern-tundra", "hill4.png"),
      pk("northern-tundra", "hill5.png"),
      pk("northern-tundra", "hill6.png"),
    ],
    wreckage: [
      pk("northern-tundra", "burned-down-cabin.png"),
      pk("northern-tundra", "damaged-cabin.png"),
      pk("northern-tundra", "masa.png"),
    ],
    // Bias toward single pines so dense forests read as many trunks, not overlapping mega-groves.
    trees: [
      pk("northern-tundra", "tree1.png"),
      pk("northern-tundra", "tree1.png"),
      pk("northern-tundra", "tree2.png"),
      pk("northern-tundra", "tree2.png"),
      pk("northern-tundra", "tree3.png"),
      pk("northern-tundra", "tree3.png"),
      pk("northern-tundra", "tree-dead.png"),
      pk("northern-tundra", "trees-group2.png"),
      pk("northern-tundra", "trees-group3.png"),
      pk("northern-tundra", "trees-group4.png"),
      pk("northern-tundra", "trees-group1.png"),
    ],
    road: [],
    clear: [],
  },
  "open-fields": {
    wall: [pk("open-fields", "trench.png"), pk("open-fields", "log.png")],
    building: [
      pk("open-fields", "barn.png"),
      pk("open-fields", "bunker.png"),
      pk("open-fields", "house.png"),
      pk("open-fields", "damaged-house.png"),
      pk("open-fields", "damaged-chirch.png"),
      pk("open-fields", "supply-cash.png"),
    ],
    rubble: [
      pk("open-fields", "bolders.png"),
      pk("open-fields", "scatterd-rocks.png"),
      pk("open-fields", "large-rock.png"),
      pk("open-fields", "stump1.png"),
      pk("open-fields", "stump2.png"),
    ],
    crater: [
      pk("open-fields", "hill1.png"),
      pk("open-fields", "hill2.png"),
      pk("open-fields", "hill3.png"),
      pk("open-fields", "hill4.png"),
      pk("open-fields", "hill5.png"),
      pk("open-fields", "hill6.png"),
      pk("open-fields", "hill7.png"),
      pk("open-fields", "blast-craters.png"),
    ],
    wreckage: [pk("open-fields", "ruin.png"), pk("open-fields", "dead-tree.png")],
    trees: [
      pk("open-fields", "trees-group1.png"),
      pk("open-fields", "trees-group2.png"),
      pk("open-fields", "trees-group3.png"),
      pk("open-fields", "tree1.png"),
      pk("open-fields", "three2.png"),
      pk("open-fields", "three3.png"),
      pk("open-fields", "bush.png"),
      pk("open-fields", "bush2.png"),
      pk("open-fields", "bush3.png"),
    ],
    road: [],
    clear: [],
  },
  "urban-combat": {
    wall: [
      pk("urban-combat", "wall.png"),
      pk("urban-combat", "damaged-wall1.png"),
      pk("urban-combat", "damaged-wall2.png"),
      pk("urban-combat", "damaged-wall3.png"),
      pk("urban-combat", "ruin-wall.png"),
      pk("urban-combat", "road-wall-single.png"),
      pk("urban-combat", "road-wall-duble.png"),
      pk("urban-combat", "rock-bin-wall.png"),
      pk("urban-combat", "damaged-road-wall.png"),
      // Sandbags kept rare — only one entry so they don't dominate wall rolls
      pk("urban-combat", "sand-bag-wall.png"),
    ],
    building: [
      pk("urban-combat", "ruin-structure1.png"),
      pk("urban-combat", "ruin-structure2.png"),
      pk("urban-combat", "ruin-structure3.png"),
      pk("urban-combat", "ruin-structure4.png"),
      pk("urban-combat", "ruin-structure5.png"),
      pk("urban-combat", "ruin-structure6.png"),
      pk("urban-combat", "ruin-structure7.png"),
      pk("urban-combat", "ruin-structure8.png"),
      pk("urban-combat", "ruin-shop.png"),
      pk("urban-combat", "ruin-shop2.png"),
      pk("urban-combat", "town-square.png"),
      pk("urban-combat", "shrine.png"),
      pk("urban-combat", "shantey.png"),
      pk("urban-combat", "bus-stop.png"),
    ],
    rubble: [
      pk("urban-combat", "debree-field1.png"),
      pk("urban-combat", "debree-field2.png"),
      pk("urban-combat", "debree-field3.png"),
      pk("urban-combat", "debree-field4.png"),
      pk("urban-combat", "debree-field5.png"),
      pk("urban-combat", "debree-field7.png"),
      pk("urban-combat", "debree-field8.png"),
      pk("urban-combat", "debree.png"),
      pk("urban-combat", "scatter.png"),
      pk("urban-combat", "random-scatter.png"),
      pk("urban-combat", "rubble-cross.png"),
      pk("urban-combat", "pile-of-tires.png"),
      pk("urban-combat", "pile-of-boxes.png"),
      pk("urban-combat", "stacked-boxes.png"),
      pk("urban-combat", "empty-berrals.png"),
      pk("urban-combat", "two-berrals.png"),
    ],
    crater: [pk("urban-combat", "blast-crater.png")],
    wreckage: [
      pk("urban-combat", "broke-down-truck.png"),
      pk("urban-combat", "damaged-monument.png"),
      pk("urban-combat", "damaged-piller.png"),
      pk("urban-combat", "damged-piller2.png"),
      pk("urban-combat", "damaged-piller3.png"),
      pk("urban-combat", "ruin-stairs.png"),
      pk("urban-combat", "equipment-cash.png"),
      pk("urban-combat", "large-supply-cash.png"),
      pk("urban-combat", "bollard.png"),
      pk("urban-combat", "light-pole.png"),
      pk("urban-combat", "power-pole.png"),
      pk("urban-combat", "street-light.png"),
      pk("urban-combat", "bilbord.png"),
      pk("urban-combat", "tent.png"),
      pk("urban-combat", "sand-bag-cover.png"),
    ],
    trees: [pk("urban-combat", "walled-guarden1.png"), pk("urban-combat", "walled-guarden2.png")],
    road: [],
    clear: [],
  },
};

export function terrainSpritesForMap(mapId?: string | null): Record<string, string[]> {
  return TERRAIN_SPRITES_BY_PACK[terrainPackForMap(mapId)];
}

/** On-map draw size. Prefer heightR, or pxPerR for packs whose art is already relatively scaled. */
export type TerrainDrawScale = {
  heightR?: number;
  maxWidthR?: number;
  /** Hex radius in source pixels — preserves native relative sizes across widgets. */
  pxPerR?: number;
};

const DEFAULT_TERRAIN_SCALE: Record<string, TerrainDrawScale> = {
  building: { heightR: 2.4, maxWidthR: 3.0 },
  wall: { heightR: 0.85, maxWidthR: 1.8 },
  wreckage: { heightR: 1.0, maxWidthR: 2.0 },
  trees: { heightR: 1.2, maxWidthR: 2.2 },
  rubble: { heightR: 0.7, maxWidthR: 2.0 },
  crater: { heightR: 0.45, maxWidthR: 2.0 },
  road: { heightR: 0.3, maxWidthR: 1.2 },
  clear: { heightR: 0.3, maxWidthR: 1.2 },
};

/**
 * Urban art is authored with correct relative pixel scale (Raymond's battleground example).
 * Map the tallest ruin (~348px) to ~2.75R and apply that same px→world factor to every widget.
 */
const URBAN_REF_PX_HEIGHT = 348;
const URBAN_REF_HEIGHT_R = 2.75;
const URBAN_PX_PER_R = URBAN_REF_PX_HEIGHT / URBAN_REF_HEIGHT_R;

function fileNameFromUrl(url: string): string {
  const clean = url.split("?")[0] || url;
  const parts = clean.split("/");
  return parts[parts.length - 1] || clean;
}

/** Tundra pines: singles ~194px → ~1.55R; groups keep relative size without smothering hexes. */
const TUNDRA_TREE_SCALE: TerrainDrawScale = { heightR: 1.55, maxWidthR: 2.15 };
const TUNDRA_BUILDING_SCALE: TerrainDrawScale = { heightR: 2.35, maxWidthR: 2.8 };
const TUNDRA_WALL_SCALE: TerrainDrawScale = { heightR: 0.9, maxWidthR: 2.2 };
const TUNDRA_RUBBLE_SCALE: TerrainDrawScale = { heightR: 0.75, maxWidthR: 2.0 };
const TUNDRA_CRATER_SCALE: TerrainDrawScale = { heightR: 0.55, maxWidthR: 2.2 };
const TUNDRA_WRECKAGE_SCALE: TerrainDrawScale = { heightR: 1.15, maxWidthR: 2.3 };

export function terrainDrawScale(
  mapId: string | null | undefined,
  terrainId: string,
  _spriteUrl: string,
): TerrainDrawScale {
  const pack = terrainPackForMap(mapId);
  if (pack === "urban-combat") {
    return { pxPerR: URBAN_PX_PER_R, maxWidthR: 3.5 };
  }
  if (pack === "northern-tundra") {
    if (terrainId === "trees") return TUNDRA_TREE_SCALE;
    if (terrainId === "building") return TUNDRA_BUILDING_SCALE;
    if (terrainId === "wall") return TUNDRA_WALL_SCALE;
    if (terrainId === "rubble") return TUNDRA_RUBBLE_SCALE;
    if (terrainId === "crater") return TUNDRA_CRATER_SCALE;
    if (terrainId === "wreckage") return TUNDRA_WRECKAGE_SCALE;
  }
  return DEFAULT_TERRAIN_SCALE[terrainId] || { heightR: 1.0, maxWidthR: 2.0 };
}

/** Compute uniform sprite scale from texture size and intended on-map footprint. */
export function terrainSpriteScaleFactor(
  textureWidth: number,
  textureHeight: number,
  hexR: number,
  draw: TerrainDrawScale,
): number {
  let scale: number;
  if (draw.pxPerR && draw.pxPerR > 0) {
    scale = hexR / draw.pxPerR;
  } else {
    const targetH = hexR * (draw.heightR ?? 1.0);
    scale = targetH / Math.max(textureHeight, 1);
  }
  if (draw.maxWidthR != null) {
    const maxW = hexR * draw.maxWidthR;
    const w = textureWidth * scale;
    if (w > maxW) scale = maxW / Math.max(textureWidth, 1);
  }
  return scale;
}
