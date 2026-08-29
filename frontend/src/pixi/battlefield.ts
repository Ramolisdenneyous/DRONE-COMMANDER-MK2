import { Application, Assets, Container, Graphics, Sprite, Text, Texture } from "pixi.js";
import { playSfx, playSfxBed, stopAudio, fireSfxForAttack } from "../audio/sfx";
import {
  flashUnitSprite,
  playExplosionBurst,
  playHitBurst,
  playTracer,
  preloadAoeBlast,
  type CombatFxKind,
  VOLLEY_CAP_MS,
  VOLLEY_STAGGER_MS,
} from "./combatFx";
import { terrainDrawScale, terrainSpriteScaleFactor, terrainSpritesForMap } from "./terrainSprites";
import {
  moveFrameUrls,
  shootFrameUrls,
  deployFrameUrls,
  unitAmmoEmpty,
  unitArtFace,
  unitPortraitUrl,
  unitReadyUrl,
  unitSpriteTargetHeight,
  resolveAssetSetId,
} from "./unitSprites";

export { unitPortraitUrl, unitAmmoEmpty } from "./unitSprites";

const R = 36; // slightly tighter for readable 50x50 overview
const ISO_Y_SCALE = 0.72;
const SQRT3 = Math.sqrt(3);
const MIN_ZOOM = 0.35;
/**
 * Phone default mid-zoom: hex columns across the field.
 * (Earlier 11 was ~20 hexes too tight vs Raymond's preferred default.)
 */
const PHONE_MID_HEXES = 31;
const PHONE_MAX_WIDTH = 480;
const HEX_COL_WIDTH = R * SQRT3;

/** odd-r offset (col,row) → axial */
function offsetToAxial(col: number, row: number): { q: number; r: number } {
  const q = col - (row - (row & 1)) / 2;
  const r = row;
  return { q, r };
}

function hexDistance(col1: number, row1: number, col2: number, row2: number): number {
  const a = offsetToAxial(col1, row1);
  const b = offsetToAxial(col2, row2);
  const dq = a.q - b.q;
  const dr = a.r - b.r;
  return (Math.abs(dq) + Math.abs(dr) + Math.abs(dq + dr)) / 2;
}
const MAX_ZOOM = 1.75;

export type Hex = { q: number; r: number };

/**
 * Map hex → screen. Hex(q,r) is odd-r offset (col, row) so a W×H grid
 * draws as a rectangular tabletop battlemat (brick stagger by row).
 */
export function axialToScreen(q: number, r: number, radius = R): { x: number; y: number } {
  const x = radius * SQRT3 * (q + 0.5 * (r & 1));
  const y = radius * 1.5 * r;
  return { x, y: y * ISO_Y_SCALE };
}

export type BattlefieldHost = {
  destroy: () => void;
  hydrate: (battle: any) => Promise<void>;
  setSelection: (unitId: string | null) => void;
  setInteractable: (ok: boolean) => void;
  setPlacementHexes: (hexes: Hex[] | null) => void;
  centerOnActive: () => void;
  centerOnMap: () => void;
  centerOnUnit: (unitId: string) => void;
  /** Zoom in for playable hex clicking if currently at deploy overview. */
  ensurePlayZoom: (unitId?: string | null) => void;
  /** Max zoom on a unit (control phase on phone). */
  zoomToMaxOnUnit: (unitId: string) => void;
  zoomBy: (factor: number) => void;
  playMoveAnimation: (args: {
    unitId: string;
    path: Hex[];
    side?: string;
    label?: string;
    assetSetId?: string;
    definitionId?: string;
    category?: string;
    commanderAvatar?: string;
    ammo?: Record<string, number>;
    modelPaths?: { model_id: string; path: Hex[]; to?: Hex }[];
  }) => Promise<void>;
  playAttackFlash: (from: Hex, to: Hex) => Promise<void>;
  playSquadVolley: (shots: { from: Hex; to: Hex }[]) => Promise<void>;
  playDeployMine: (args: {
    unitId: string;
    to: Hex;
    side?: string;
    assetSetId?: string;
    definitionId?: string;
    category?: string;
  }) => Promise<void>;
  playCombatFx: (args: {
    shots?: { from: Hex; to: Hex; hit?: boolean }[];
    kind?: CombatFxKind;
    hits?: Hex[];
    blast?: Hex | null;
    weaponId?: string;
    actorCategory?: string;
    commanderAvatar?: string;
    actorSide?: string;
    actorAssetSetId?: string;
    actorDefinitionId?: string;
  }) => Promise<void>;
};

type Handlers = {
  onHexSelected?: (hex: Hex) => void;
  onUnitSelected?: (unitId: string) => void;
  onIntroScan?: (playing: boolean) => void;
  onRamAllocate?: (droneId: string) => void;
  onRamReclaim?: (droneId: string) => void;
  onLoadProgress?: (percent: number) => void;
  /** Fired once map art/units are drawn — before hex-scan intro animation. */
  onAssetsReady?: () => void;
};

const RAM_ICON_URL = "/assets/ui/ram_icon.png";

async function loadChromaTexture(url: string, cache: Map<string, Texture>): Promise<Texture> {
  if (cache.has(url)) return cache.get(url)!;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}`);
  const blob = await res.blob();
  const bmp = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bmp.width;
  canvas.height = bmp.height;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bmp, 0, 0);
  const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = img.data;
  const w = canvas.width;
  const h = canvas.height;
  const n = w * h;

  // Only chroma-key near-black studio backdrop that touches the image border.
  // A blanket "all near-black → transparent" pass punches holes through dark
  // armor, shadows, and rifle barrels in the middle of unit art.
  const isKey = (i: number) => {
    const o = i * 4;
    const a = d[o + 3];
    if (a < 8) return false; // already transparent
    const r = d[o];
    const g = d[o + 1];
    const b = d[o + 2];
    return r < 22 && g < 22 && b < 22;
  };

  const visited = new Uint8Array(n);
  const stack: number[] = [];
  const pushEdge = (x: number, y: number) => {
    const i = y * w + x;
    if (visited[i] || !isKey(i)) return;
    visited[i] = 1;
    stack.push(i);
  };
  for (let x = 0; x < w; x++) {
    pushEdge(x, 0);
    pushEdge(x, h - 1);
  }
  for (let y = 0; y < h; y++) {
    pushEdge(0, y);
    pushEdge(w - 1, y);
  }

  while (stack.length) {
    const i = stack.pop()!;
    d[i * 4 + 3] = 0;
    const x = i % w;
    const y = (i / w) | 0;
    if (x > 0) {
      const j = i - 1;
      if (!visited[j] && isKey(j)) {
        visited[j] = 1;
        stack.push(j);
      }
    }
    if (x + 1 < w) {
      const j = i + 1;
      if (!visited[j] && isKey(j)) {
        visited[j] = 1;
        stack.push(j);
      }
    }
    if (y > 0) {
      const j = i - w;
      if (!visited[j] && isKey(j)) {
        visited[j] = 1;
        stack.push(j);
      }
    }
    if (y + 1 < h) {
      const j = i + w;
      if (!visited[j] && isKey(j)) {
        visited[j] = 1;
        stack.push(j);
      }
    }
  }

  ctx.putImageData(img, 0, 0);
  const texture = Texture.from(canvas);
  cache.set(url, texture);
  return texture;
}

export async function createBattlefield(
  host: HTMLElement,
  handlers: Handlers = {}
): Promise<BattlefieldHost> {
  handlers.onLoadProgress?.(4);
  const app = new Application();
  await app.init({
    background: "#050607",
    resizeTo: host,
    antialias: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
    autoDensity: true,
  });
  handlers.onLoadProgress?.(12);
  host.innerHTML = "";
  host.appendChild(app.canvas);
  app.canvas.style.width = "100%";
  app.canvas.style.height = "100%";

  const camera = new Container();
  app.stage.addChild(camera);

  /** All board art lives here; masked to the hex playfield AABB so sand can't spill into letterbox. */
  const world = new Container();
  camera.addChild(world);
  const playfieldMask = new Graphics();
  camera.addChild(playfieldMask);

  const layers: Record<string, Container> = {
    ground_base: new Container(),
    ground_decals: new Container(),
    hex_grid: new Container(),
    terrain_ground: new Container(),
    terrain_structures: new Container(),
    hex_overlays: new Container(),
    units: new Container(),
    ram_badges: new Container(),
    effects_world: new Container(),
    objectives_and_labels: new Container(),
    battlefield_hud: new Container(),
  };
  Object.values(layers).forEach((c) => world.addChild(c));
  world.mask = playfieldMask;
  layers.effects_world.sortableChildren = true;
  preloadAoeBlast();

  let battle: any = null;
  let selectedId: string | null = null;
  let wantInteractable = true;
  let interactable = true;
  let placementHexes: Hex[] | null = null;
  let didInitialFrame = false;
  let zoom = 0.55;
  camera.scale.set(zoom);
  const textureCache = new Map<string, Texture>();
  let lastActiveId: string | null = null;
  let introPlaying = false;
  let moveAnimating = false;
  let unitsDrawGen = 0;
  /** Living model containers on the board: `${unitId}::${modelId}` → Container */
  const modelRegistry = new Map<string, Container>();
  let introPlayedBattleId: string | null = null;
  let gridPulseEnabled = true;
  /** Last horizontal facing per unit: 1 = sprite natural (right), -1 = flipped (left). */
  const facingByUnit = new Map<string, 1 | -1>();
  let ramDrag: {
    from: "commander" | "drone";
    droneId?: string;
    ghost: Sprite;
  } | null = null;

  function defaultFacing(side?: string): 1 | -1 {
    // Face each other across the field until they move
    return side === "opposition" ? -1 : 1;
  }

  function facingFor(unitId: string, side?: string): 1 | -1 {
    return facingByUnit.get(unitId) ?? defaultFacing(side);
  }

  function facingFromPath(path: Hex[]): 1 | -1 {
    if (path.length < 2) return 1;
    // Prefer the last meaningful screen-x step so short jogs still count
    for (let i = path.length - 1; i >= 1; i--) {
      const a = axialToScreen(path[i - 1].q, path[i - 1].r);
      const b = axialToScreen(path[i].q, path[i].r);
      const dx = b.x - a.x;
      if (Math.abs(dx) > 0.5) return dx < 0 ? -1 : 1;
    }
    return 1;
  }

  // Blue hex grid power surge: dim → bright → dim, 6s cycle (after intro)
  const GRID_ALPHA_DIM = 0.22;
  const GRID_ALPHA_BRIGHT = 0.75;
  const GRID_SURGE_MS = 6000;
  let gridSurgeElapsedMs = 0;
  const pulseHexGrid = () => {
    const grid = layers.hex_grid;
    if (!grid.children.length || !gridPulseEnabled) return;
    const phase = (gridSurgeElapsedMs % GRID_SURGE_MS) / GRID_SURGE_MS;
    const wave = 0.5 + 0.5 * Math.sin(phase * Math.PI * 2 - Math.PI / 2);
    grid.alpha = GRID_ALPHA_DIM + (GRID_ALPHA_BRIGHT - GRID_ALPHA_DIM) * wave;
  };
  const onGridTicker = (ticker: { deltaMS: number }) => {
    if (!gridPulseEnabled) return;
    gridSurgeElapsedMs += ticker.deltaMS;
    pulseHexGrid();
  };
  app.ticker.add(onGridTicker);
  layers.hex_grid.alpha = GRID_ALPHA_DIM;

  /** Tight AABB of the flat-top hex playfield (outer polygon corners). */
  function mapBounds(width: number, height: number) {
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    const includeHex = (q: number, r: number) => {
      const p = axialToScreen(q, r);
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 180) * (60 * i - 30);
        const x = p.x + R * Math.cos(angle);
        const y = p.y + R * ISO_Y_SCALE * Math.sin(angle);
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      }
    };
    for (let q = 0; q < width; q++) {
      includeHex(q, 0);
      if (height > 1) includeHex(q, height - 1);
    }
    for (let r = 1; r < height - 1; r++) {
      includeHex(0, r);
      if (width > 1) includeHex(width - 1, r);
    }
    if (!Number.isFinite(minX)) {
      minX = 0;
      maxX = 1;
      minY = 0;
      maxY = 1;
    }
    return { minX, maxX, minY, maxY, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 };
  }

  function viewportSize() {
    // Canvas client box is the true drawable area (avoids host/rect mismatches).
    const cw = app.canvas?.clientWidth || 0;
    const ch = app.canvas?.clientHeight || 0;
    const rect = host.getBoundingClientRect();
    const w = Math.max(1, Math.floor(cw || rect.width || app.screen.width || 1));
    const h = Math.max(1, Math.floor(ch || rect.height || app.screen.height || 1));
    return { w, h };
  }

  /** Overview zoom shows the full playfield (contain), including both deployment belts. */
  let overviewZoom = MIN_ZOOM;
  let mapLocked = true;

  function focusWorld(x: number, y: number) {
    const { w, h } = viewportSize();
    camera.x = w / 2 - x * zoom;
    camera.y = h / 2 - y * zoom;
    clampCameraToMap();
  }

  function isPhoneViewport(): boolean {
    const { w } = viewportSize();
    if (w > 0 && w <= PHONE_MAX_WIDTH) return true;
    if (typeof window !== "undefined" && window.matchMedia) {
      return window.matchMedia(`(max-width: ${PHONE_MAX_WIDTH}px)`).matches;
    }
    return false;
  }

  /** Default framing after intro / round: phone mid, desktop full-board contain. */
  function fitDeployOverview(lock = true): boolean {
    const mode = isPhoneViewport() ? "phone-mid" : "contain";
    return centerOnMap({ fit: true, mode, lock });
  }

  /**
   * When zoomed in past overview, keep the map covering the view.
   * At overview (contain), center the board and allow side letterboxing.
   */
  function clampCameraToMap() {
    if (!battle) return;
    const b = mapBounds(battle.map?.width || 50, battle.map?.height || 50);
    const { w, h } = viewportSize();
    const mapW = (b.maxX - b.minX) * zoom;
    const mapH = (b.maxY - b.minY) * zoom;

    if (mapW <= w + 0.5) {
      camera.x = w / 2 - b.cx * zoom;
    } else {
      const minCamX = w - b.maxX * zoom;
      const maxCamX = -b.minX * zoom;
      camera.x = Math.min(maxCamX, Math.max(minCamX, camera.x));
    }

    if (mapH <= h + 0.5) {
      camera.y = h / 2 - b.cy * zoom;
    } else {
      const minCamY = h - b.maxY * zoom;
      const maxCamY = -b.minY * zoom;
      camera.y = Math.min(maxCamY, Math.max(minCamY, camera.y));
    }
  }

  /** World focus for phone mid: living units → objective → map center. */
  function battleFocusWorld(): { x: number; y: number } {
    const mapWhex = battle?.map?.width || 50;
    const mapHhex = battle?.map?.height || 50;
    const b = mapBounds(mapWhex, mapHhex);
    const units = [...(battle?.friendly_units || []), ...(battle?.opposition_units || [])].filter(
      (u: any) => u?.alive !== false && u?.position
    );
    if (units.length) {
      let sx = 0;
      let sy = 0;
      for (const u of units) {
        const p = axialToScreen(u.position.q, u.position.r);
        sx += p.x;
        sy += p.y;
      }
      return { x: sx / units.length, y: sy / units.length };
    }
    const zone = (battle?.objective_zones || []).find((z: any) => z?.id === "center") || battle?.objective_zones?.[0];
    if (zone && Number.isFinite(zone.q) && Number.isFinite(zone.r)) {
      return axialToScreen(zone.q, zone.r);
    }
    return { x: b.cx, y: b.cy };
  }

  /** Full-board contain — zoom-out floor on every device. */
  function computeContainZoom(): number | null {
    if (!battle) return null;
    const mapWhex = battle.map?.width || 50;
    const mapHhex = battle.map?.height || 50;
    const b = mapBounds(mapWhex, mapHhex);
    const { w: screenW, h: screenH } = viewportSize();
    if (screenW < 32 || screenH < 32) return null;
    const mapW = Math.max(1, b.maxX - b.minX);
    const mapH = Math.max(1, b.maxY - b.minY);
    const pad = 12;
    return Math.max(0.05, Math.min((screenW - pad * 2) / mapW, (screenH - pad * 2) / mapH));
  }

  /** Phone default mid (~PHONE_MID_HEXES columns). May be below MIN_ZOOM. */
  function computePhoneMidZoom(screenW: number): number {
    const pad = 8;
    const worldW = PHONE_MID_HEXES * HEX_COL_WIDTH;
    return Math.max(0.05, Math.min(MAX_ZOOM, (screenW - pad * 2) / worldW));
  }

  /** Keep overviewZoom = full-board contain (never the mid default). */
  function refreshOverviewFloor() {
    const contain = computeContainZoom();
    if (contain != null) overviewZoom = contain;
  }

  /**
   * Fit/center the rectangular playfield.
   * contain = full board (zoom-out floor); phone-mid = default phone framing; cover = fill axes.
   */
  function centerOnMap(
    opts?: { fit?: boolean; mode?: "cover" | "contain" | "phone-mid"; lock?: boolean }
  ): boolean {
    if (!battle) return false;
    const mapWhex = battle.map?.width || 50;
    const mapHhex = battle.map?.height || 50;
    const b = mapBounds(mapWhex, mapHhex);
    const { w: screenW, h: screenH } = viewportSize();
    if (screenW < 32 || screenH < 32) return false;

    let mode = opts?.mode;
    if (!mode) mode = isPhoneViewport() ? "phone-mid" : "contain";

    // Always know how far out the player can go.
    refreshOverviewFloor();

    if (opts?.fit !== false) {
      const mapW = Math.max(1, b.maxX - b.minX);
      const mapH = Math.max(1, b.maxY - b.minY);
      let fit: number;
      if (mode === "phone-mid") {
        fit = computePhoneMidZoom(screenW);
      } else if (mode === "contain") {
        fit = overviewZoom;
      } else {
        fit = Math.max(screenW / mapW, screenH / mapH);
      }
      zoom = Math.max(0.05, fit);
      camera.scale.set(zoom);
    }

    const focus = mode === "phone-mid" ? battleFocusWorld() : { x: b.cx, y: b.cy };
    focusWorld(focus.x, focus.y);
    clampCameraToMap();
    // Full-board contain can lock; mid crops so pan stays free.
    if (mode === "contain" && opts?.lock !== false) {
      mapLocked = true;
    } else {
      mapLocked = false;
    }
    return true;
  }

  function scheduleCenterOnMap(attempt = 0) {
    requestAnimationFrame(() => {
      const ok = fitDeployOverview(true);
      if (!ok && attempt < 12) {
        // Host/canvas often still 0×0 for a few frames after mount/intro.
        requestAnimationFrame(() => scheduleCenterOnMap(attempt + 1));
      }
    });
  }

  /** After hex scan intro — control phase on phone needs max zoom on commander, not overview. */
  function finishIntroFraming() {
    const cp = battle?.control_phase;
    const inFriendlyCp = !!(cp?.active && cp?.side === "friendly");
    if (isPhoneViewport() && inFriendlyCp) {
      const cmdId =
        cp?.commander_id ||
        battle?.commander?.unit_instance_id ||
        battle?.active_actor_id;
      if (cmdId) {
        zoomToMaxOnUnit(cmdId);
        return;
      }
    }
    scheduleCenterOnMap();
  }

  function scheduleFinishIntroFraming() {
    // Defer two frames so host layout/size is final before framing.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => finishIntroFraming());
    });
  }

  function centerOnActive() {
    if (!battle) return;
    const active =
      [...(battle.friendly_units || []), ...(battle.opposition_units || [])].find(
        (u: any) => u.unit_instance_id === battle.active_actor_id
      ) || battle.commander;
    if (!active?.position) return;
    mapLocked = false;
    const p = axialToScreen(active.position.q, active.position.r);
    focusWorld(p.x, p.y);
    clampCameraToMap();
  }

  function centerOnUnit(unitId: string) {
    if (!battle) return;
    const u = [...(battle.friendly_units || []), ...(battle.opposition_units || [])].find(
      (x: any) => x.unit_instance_id === unitId
    );
    if (!u?.position) return;
    mapLocked = false;
    const p = axialToScreen(u.position.q, u.position.r);
    focusWorld(p.x, p.y);
    clampCameraToMap();
  }

  /** If zoomed all the way out, bring phone to mid (or desktop play zoom) for hex clicks. */
  function ensurePlayZoom(unitId?: string | null) {
    if (!battle) return;
    const { w } = viewportSize();
    refreshOverviewFloor();
    const maxZ = Math.max(MAX_ZOOM, overviewZoom * 3);
    const phoneMid = computePhoneMidZoom(w);
    const target = isPhoneViewport()
      ? Math.min(maxZ, Math.max(phoneMid, overviewZoom + 0.02))
      : Math.min(maxZ, Math.max(overviewZoom * 2.1, overviewZoom + 0.08));
    // Only lift when near full zoom-out — don't yank if already at mid/play zoom.
    if (zoom <= overviewZoom * 1.12) {
      zoom = target;
      camera.scale.set(zoom);
      mapLocked = false;
    }
    if (unitId) centerOnUnit(unitId);
    else centerOnActive();
  }

  /** Control Phase on phone: max zoom centered on commander so RAM icons are readable. */
  function zoomToMaxOnUnit(unitId: string) {
    if (!battle) return;
    const u = [...(battle.friendly_units || []), ...(battle.opposition_units || [])].find(
      (x: any) => x.unit_instance_id === unitId
    );
    if (!u?.position) return;
    refreshOverviewFloor();
    const maxZ = Math.max(MAX_ZOOM, overviewZoom * 3);
    zoom = maxZ;
    camera.scale.set(zoom);
    mapLocked = false;
    const p = axialToScreen(u.position.q, u.position.r);
    focusWorld(p.x, p.y);
    clampCameraToMap();
  }

  function sleep(ms: number) {
    return new Promise<void>((resolve) => setTimeout(resolve, ms));
  }

  async function playMoveAnimation(args: {
    unitId: string;
    path: Hex[];
    side?: string;
    label?: string;
    assetSetId?: string;
    definitionId?: string;
    category?: string;
    commanderAvatar?: string;
    ammo?: Record<string, number>;
    modelPaths?: { model_id: string; path: Hex[]; to?: Hex }[];
  }) {
    const jobs =
      args.modelPaths && args.modelPaths.length
        ? args.modelPaths
            .map((mp, i) => ({
              modelId: String(mp.model_id || `m${i + 1}`),
              path: (mp.path?.length ? mp.path : mp.to ? [mp.to] : args.path) as Hex[],
            }))
            .filter((j) => j.path.length >= 2)
        : args.path?.length >= 2
          ? [{ modelId: "m1", path: args.path }]
          : [];

    if (!jobs.length) {
      if (args.path?.length) {
        const p = axialToScreen(args.path[0].q, args.path[0].r);
        focusWorld(p.x, p.y);
        await sleep(280);
      }
      return;
    }

    // Cancel any in-flight drawUnits that would recreate ready ghosts mid-move
    moveAnimating = true;
    unitsDrawGen += 1;

    const isSquad = jobs.length > 1;
    const BUDGET_MS = isSquad ? 6000 : Math.min(2200, Math.max(700, jobs[0].path.length * 200));
    const staggerWindow = isSquad ? BUDGET_MS * 0.5 : 0;
    const walkMs = isSquad ? Math.max(450, BUDGET_MS - staggerWindow - 100) : BUDGET_MS;

    const accent = args.side === "opposition" ? 0xff6655 : 0x66ddff;
    const walkUrls = moveFrameUrls(
      args.assetSetId,
      args.category,
      args.side,
      args.commanderAvatar,
      unitAmmoEmpty({ ammo: args.ammo }),
      args.definitionId,
    );
    let walkFrames: Texture[] = [];
    if (walkUrls.length) {
      try {
        walkFrames = await Promise.all(walkUrls.map((url) => loadChromaTexture(url, textureCache)));
      } catch {
        walkFrames = [];
      }
    }

    const resolveContainer = (modelId: string, start: Hex): Container | null => {
      const keyed = modelRegistry.get(modelKey(args.unitId, modelId));
      if (keyed && !(keyed as any).destroyed) return keyed;
      const sx = axialToScreen(start.q, start.r);
      let best: Container | null = null;
      let bestD = Infinity;
      for (const c of layers.units.children) {
        const cc = c as any;
        if (cc.unitId !== args.unitId) continue;
        if (String(cc.modelId) === modelId) return c as Container;
        const dx = c.x - sx.x;
        const dy = c.y - sx.y;
        const d = dx * dx + dy * dy;
        if (d < bestD) {
          bestD = d;
          best = c as Container;
        }
      }
      return best;
    };

    /** One tracked actor: this man's container does Ready→Walk→Ready by itself. */
    const animateOne = async (job: { modelId: string; path: Hex[] }, index: number) => {
      const delay =
        isSquad && jobs.length > 1
          ? (index / (jobs.length - 1)) * staggerWindow + (Math.random() - 0.5) * 140
          : 0;
      if (delay > 0) await sleep(Math.max(0, delay));

      const container = resolveContainer(job.modelId, job.path[0]);
      if (!container || (container as any).destroyed) return;

      const screenPts = job.path.map((h) => axialToScreen(h.q, h.r));
      const readySpr = container.children.find((c) => (c as any).role === "ready") as Sprite | undefined;

      let walkSpr: Sprite | null = null;
      let baseScale = 1;
      if (walkFrames.length) {
        walkSpr = new Sprite(walkFrames[0]);
        walkSpr.anchor.set(0.5, 0.92);
        const targetH = unitSpriteTargetHeight(R, {
          category: args.category,
          assetSetId: args.assetSetId,
          side: args.side,
          definitionId: args.definitionId,
        });
        baseScale = targetH / Math.max(walkSpr.texture.height, 1);
        walkSpr.scale.set(baseScale);
        (walkSpr as any).role = "walk";
        container.addChild(walkSpr);
      } else {
        const proxy = new Graphics()
          .ellipse(0, 8, R * 0.5, R * 0.26)
          .stroke({ width: 2.5, color: accent, alpha: 1 });
        (proxy as any).role = "walk";
        container.addChild(proxy);
        const disc = new Graphics().circle(0, -4, 10).fill({ color: accent, alpha: 0.85 });
        (disc as any).role = "walk";
        container.addChild(disc);
      }

      // Ready → Move for THIS man only
      if (readySpr) readySpr.visible = false;
      for (const ch of container.children) {
        if ((ch as any).role === "ready" || (ch as any).role === "walk") continue;
        if (ch instanceof Text) ch.visible = false;
      }

      const FRAME_MS = walkFrames.length > 6 ? 70 : 90;
      let frameIdx = 0;
      let lastFrameAt = performance.now();
      const t0 = performance.now();

      await new Promise<void>((resolve) => {
        const tick = () => {
          if ((container as any).destroyed) {
            resolve();
            return;
          }
          const now = performance.now();
          const t = Math.min(1, (now - t0) / walkMs);
          const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
          const f = eased * (screenPts.length - 1);
          const i = Math.floor(f);
          const frac = f - i;
          const a = screenPts[i];
          const b = screenPts[Math.min(i + 1, screenPts.length - 1)];
          container.x = a.x + (b.x - a.x) * frac;
          container.y = a.y + (b.y - a.y) * frac;

          if (walkSpr && walkFrames.length) {
            const dx = b.x - a.x;
            const face: 1 | -1 = dx < -0.5 ? -1 : dx > 0.5 ? 1 : facingFor(args.unitId, args.side);
            facingByUnit.set(modelKey(args.unitId, job.modelId), face);
            const artFace = unitArtFace(args.assetSetId, args.category, args.commanderAvatar, args.definitionId);
            walkSpr.scale.set(baseScale * face * artFace, baseScale);
            if (now - lastFrameAt >= FRAME_MS) {
              frameIdx = (frameIdx + 1) % walkFrames.length;
              walkSpr.texture = walkFrames[frameIdx];
              lastFrameAt = now;
            }
          }

          // Multi-man: camera tracks only the first walker so the view doesn't jerk
          if (index === 0) focusWorld(container.x, container.y);
          if (t < 1) requestAnimationFrame(tick);
          else resolve();
        };
        requestAnimationFrame(tick);
      });

      if ((container as any).destroyed) return;

      // Move → Ready on this container at the destination hex
      for (const ch of [...container.children]) {
        if ((ch as any).role === "walk") {
          container.removeChild(ch);
          ch.destroy();
        }
      }
      if (readySpr && !(readySpr as any).destroyed) {
        const face = facingFromPath(job.path);
        facingByUnit.set(modelKey(args.unitId, job.modelId), face);
        const sc = Math.abs(readySpr.scale.y) || Math.abs(readySpr.scale.x) || 1;
        const artFace = unitArtFace(args.assetSetId, args.category, args.commanderAvatar, args.definitionId);
        readySpr.scale.set(sc * face * artFace, Math.abs(sc));
        readySpr.visible = true;
      }
      for (const ch of container.children) {
        if (ch instanceof Text) ch.visible = true;
      }
      const end = job.path[job.path.length - 1];
      (container as any).hexQ = end.q;
      (container as any).hexR = end.r;
      const endPt = axialToScreen(end.q, end.r);
      container.x = endPt.x;
      container.y = endPt.y;
    };

    try {
      clearLayer("effects_world");
      const trail = new Graphics();
      const trailPath = jobs[0].path;
      for (let i = 0; i < trailPath.length; i++) {
        const p = axialToScreen(trailPath[i].q, trailPath[i].r);
        trail.poly(hexPoints(R * 0.55).map((v, idx) => (idx % 2 === 0 ? v + p.x : v + p.y)));
        trail.fill({ color: accent, alpha: 0.08 });
      }
      layers.effects_world.addChild(trail);

      await Promise.all(jobs.map((job, index) => animateOne(job, index)));
      facingByUnit.set(args.unitId, facingFromPath(jobs[0].path));
    } finally {
      clearLayer("effects_world");
      moveAnimating = false;
    }
  }

  function containersAtHex(hex: Hex): Container[] {
    const out: Container[] = [];
    for (const c of layers.units.children) {
      const cc = c as any;
      if (Number(cc.hexQ) === hex.q && Number(cc.hexR) === hex.r) out.push(c as Container);
    }
    return out;
  }

  async function flashUnitShoot(
    from: Hex,
    to: Hex,
    side?: string,
    assetSetId?: string,
    category?: string,
    commanderAvatar?: string,
    definitionId?: string,
  ) {
    const setId = resolveAssetSetId(assetSetId, category, side, definitionId);
    const shootUrls = shootFrameUrls(setId, category, side, commanderAvatar, definitionId);
    if (!shootUrls.length) return;

    const containers = containersAtHex(from);
    if (!containers.length) return;

    let frames: Texture[] = [];
    try {
      frames = await Promise.all(shootUrls.map((url) => loadChromaTexture(url, textureCache)));
    } catch {
      return;
    }

    const a = axialToScreen(from.q, from.r);
    const b = axialToScreen(to.q, to.r);
    const dx = b.x - a.x;
    const shootFace: 1 | -1 =
      dx < -0.5 ? -1 : dx > 0.5 ? 1 : unitArtFace(setId, category, commanderAvatar, definitionId);

    const readyUrl = unitReadyUrl(
      { asset_set_id: setId, definition_id: definitionId, category, side },
      commanderAvatar,
    );
    let readyTex: Texture | null = null;
    try {
      readyTex = await loadChromaTexture(readyUrl, textureCache);
    } catch {
      readyTex = null;
    }

    const FRAME_MS = category === "commander" ? 48 : 52;
    const jobs = containers.map(async (container) => {
      const readySpr = container.children.find((c) => (c as any).role === "ready") as Sprite | undefined;
      if (!readySpr || !(readySpr instanceof Sprite)) return;
      const sc = Math.abs(readySpr.scale.y) || Math.abs(readySpr.scale.x) || 1;
      const unitId = String((container as any).unitId || "");
      const modelId = String((container as any).modelId || "");
      const faceKey = modelId ? modelKey(unitId, modelId) : unitId;
      const idleFace = facingByUnit.get(faceKey) ?? unitArtFace(setId, category, commanderAvatar, definitionId);
      const artFace = unitArtFace(setId, category, commanderAvatar, definitionId);
      for (const frame of frames) {
        readySpr.texture = frame;
        readySpr.scale.set(sc * shootFace * artFace, sc);
        await sleep(FRAME_MS);
      }
      if (readyTex) {
        readySpr.texture = readyTex;
        readySpr.scale.set(sc * idleFace * artFace, sc);
      }
    });
    await Promise.all(jobs);
  }

  async function flashUnitsAt(hexes: Hex[]) {
    const seen = new Set<string>();
    const jobs: Promise<void>[] = [];
    for (const hex of hexes) {
      const key = `${hex.q},${hex.r}`;
      if (seen.has(key)) continue;
      seen.add(key);
      for (const c of containersAtHex(hex)) jobs.push(flashUnitSprite(c));
    }
    if (jobs.length) await Promise.all(jobs);
  }

  async function playCombatFx(args: {
    shots?: { from: Hex; to: Hex; hit?: boolean }[];
    kind?: CombatFxKind;
    hits?: Hex[];
    blast?: Hex | null;
    weaponId?: string;
    actorCategory?: string;
    commanderAvatar?: string;
    actorSide?: string;
    actorAssetSetId?: string;
    actorDefinitionId?: string;
  }) {
    const kind: CombatFxKind = args.kind || "gunfire";
    const shots = args.shots || [];
    const hitHexes = [...(args.hits || [])];
    for (const s of shots) {
      if (s.hit !== false && s.to) hitHexes.push(s.to);
    }
    const blast = args.blast || (kind !== "gunfire" && shots[0]?.to ? shots[0].to : null);

    if (kind === "explosion_small") playSfx("explosion_small");
    if (kind === "explosion_large") playSfx("explosion_large");

    const fireSfx =
      kind === "gunfire"
        ? fireSfxForAttack({
            weaponId: args.weaponId,
            category: args.actorCategory,
            commanderAvatar: args.commanderAvatar,
            actorSide: args.actorSide,
          })
        : null;

    const impactJobs: Promise<void>[] = [];
    let hitSounds = 0;
    const playImpact = (hex: Hex, delayMs: number, gunHit: boolean) => {
      impactJobs.push(
        (async () => {
          if (delayMs > 0) await sleep(delayMs);
          const p = axialToScreen(hex.q, hex.r);
          if (kind === "gunfire" && gunHit) {
            if (hitSounds < 3) {
              playSfx("hit_gunfire");
              hitSounds += 1;
            }
            await Promise.all([playHitBurst(layers.effects_world, p.x, p.y), flashUnitsAt([hex])]);
          } else if (kind !== "gunfire") {
            await Promise.all([
              playExplosionBurst(layers.effects_world, p.x, p.y, kind),
              flashUnitsAt(hitHexes.length ? hitHexes : [hex]),
            ]);
          }
        })(),
      );
    };

    if (kind === "gunfire" && shots.length) {
      const n = shots.length;
      const stagger = n <= 1 ? 0 : Math.min(VOLLEY_STAGGER_MS, Math.max(22, (VOLLEY_CAP_MS - 160) / Math.max(n - 1, 1)));
      if (fireSfx) {
        if (n <= 1) {
          playSfx(fireSfx);
        } else {
          for (let i = 0; i < n; i += 1) {
            const delay = i * stagger;
            impactJobs.push(
              (async () => {
                if (delay > 0) await sleep(delay);
                playSfx(fireSfx);
              })(),
            );
          }
        }
      }
      const tracerJobs = shots.map((shot, i) => {
        const delay = i * stagger;
        const a = axialToScreen(shot.from.q, shot.from.r);
        const b = axialToScreen(shot.to.q, shot.to.r);
        if (i === 0) focusWorld(b.x, b.y);
        playImpact(shot.to, delay + 50, shot.hit !== false);
        const shootAnim =
          args.actorCategory === "soldier_squad" ||
          args.actorCategory === "commander" ||
          args.actorCategory === "drone"
            ? (async () => {
                if (delay > 0) await sleep(delay);
                await flashUnitShoot(
                  shot.from,
                  shot.to,
                  args.actorSide,
                  args.actorAssetSetId,
                  args.actorCategory,
                  args.commanderAvatar,
                  args.actorDefinitionId,
                );
              })()
            : null;
        const tracer = (async () => {
          if (delay > 0) await sleep(delay);
          await playTracer(layers.effects_world, a.x, a.y, b.x, b.y);
        })();
        return Promise.all([tracer, shootAnim].filter(Boolean) as Promise<void>[]);
      });
      await Promise.all([...tracerJobs, ...impactJobs]);
      return;
    }

    if (blast) {
      const p = axialToScreen(blast.q, blast.r);
      focusWorld(p.x, p.y);
      if (shots.length) {
        const a = axialToScreen(shots[0].from.q, shots[0].from.r);
        void playTracer(layers.effects_world, a.x, a.y, p.x, p.y);
      }
      playImpact(blast, 40, false);
      await Promise.all(impactJobs);
      return;
    }

    if (hitHexes.length) {
      const p = axialToScreen(hitHexes[0].q, hitHexes[0].r);
      focusWorld(p.x, p.y);
      await flashUnitsAt(hitHexes);
    }
  }

  async function playAttackFlash(from: Hex, to: Hex) {
    await playCombatFx({ shots: [{ from, to, hit: true }], kind: "gunfire", hits: [to] });
  }

  async function playSquadVolley(shots: { from: Hex; to: Hex }[]) {
    if (!shots.length) return;
    await playCombatFx({
      shots: shots.map((s) => ({ ...s, hit: true })),
      kind: "gunfire",
      hits: shots.map((s) => s.to),
    });
  }

  async function playDeployMine(args: {
    unitId: string;
    to: Hex;
    side?: string;
    assetSetId?: string;
    definitionId?: string;
    category?: string;
  }) {
    const unit =
      [...(battle?.friendly_units || []), ...(battle?.opposition_units || [])].find(
        (u: any) => u.unit_instance_id === args.unitId
      ) || null;
    const setId = resolveAssetSetId(
      args.assetSetId || unit?.asset_set_id,
      args.category || unit?.category,
      args.side || unit?.side,
      args.definitionId || unit?.definition_id
    );
    const urls = deployFrameUrls(
      setId,
      args.category || unit?.category,
      args.side || unit?.side,
      args.definitionId || unit?.definition_id
    );
    const from = unit?.position || args.to;
    if (urls.length && from) {
      const containers = containersAtHex(from);
      if (containers.length) {
        let frames: Texture[] = [];
        try {
          frames = await Promise.all(urls.map((url) => loadChromaTexture(url, textureCache)));
        } catch {
          frames = [];
        }
        if (frames.length) {
          const FRAME_MS = 55;
          await Promise.all(
            containers.map(async (container) => {
              const readySpr = container.children.find((c) => (c as any).role === "ready") as Sprite | undefined;
              if (!readySpr || !(readySpr instanceof Sprite)) return;
              const sc = Math.abs(readySpr.scale.y) || Math.abs(readySpr.scale.x) || 1;
              const artFace = unitArtFace(
                setId,
                args.category || unit?.category,
                undefined,
                args.definitionId || unit?.definition_id
              );
              for (const frame of frames) {
                readySpr.texture = frame;
                readySpr.scale.set(sc * artFace * artFace, sc);
                await sleep(FRAME_MS);
              }
              try {
                const readyUrl = unitReadyUrl({
                  asset_set_id: setId,
                  definition_id: args.definitionId || unit?.definition_id,
                  category: args.category || unit?.category,
                  side: args.side || unit?.side,
                });
                readySpr.texture = await loadChromaTexture(readyUrl, textureCache);
                readySpr.scale.set(sc * artFace, sc);
              } catch {
                /* keep last frame */
              }
            })
          );
        }
      }
    }
    const p = axialToScreen(args.to.q, args.to.r);
    const g = new Graphics().circle(0, 0, R * 0.35).fill({ color: 0xc9a227, alpha: 0.85 });
    g.x = p.x;
    g.y = p.y;
    layers.effects_world.addChild(g);
    await sleep(280);
    layers.effects_world.removeChild(g);
    g.destroy();
  }

  function zoomBy(factor: number) {
    const prev = zoom;
    refreshOverviewFloor();
    const maxZ = Math.max(MAX_ZOOM, overviewZoom * 3);
    const next = zoom * factor;
    // Floor = full-board contain (player can still zoom all the way out).
    zoom = Math.min(maxZ, Math.max(overviewZoom || 0.05, next));
    if (zoom <= overviewZoom * 1.001) {
      centerOnMap({ fit: true, mode: "contain", lock: true });
      return;
    }
    mapLocked = false;
    const { w, h } = viewportSize();
    const wx = (w / 2 - camera.x) / prev;
    const wy = (h / 2 - camera.y) / prev;
    camera.scale.set(zoom);
    // bypass focusWorld clamp-order; set then clamp
    camera.x = w / 2 - wx * zoom;
    camera.y = h / 2 - wy * zoom;
    clampCameraToMap();
  }

  function modelKey(unitId: string, modelId: string) {
    return `${unitId}::${modelId}`;
  }

  function clearLayer(name: string) {
    if (name === "units") modelRegistry.clear();
    const layer = layers[name];
    while (layer.children.length) {
      const child = layer.children[0];
      layer.removeChild(child);
      child.destroy({ children: true });
    }
  }

  function hexPoints(radius = R * 0.95): number[] {
    const pts: number[] = [];
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 180) * (60 * i - 30);
      pts.push(radius * Math.cos(angle), radius * ISO_Y_SCALE * Math.sin(angle));
    }
    return pts;
  }

  function setPlayfieldMask(width: number, height: number) {
    const b = mapBounds(width, height);
    playfieldMask.clear();
    playfieldMask
      .rect(b.minX, b.minY, Math.max(1, b.maxX - b.minX), Math.max(1, b.maxY - b.minY))
      .fill(0xffffff);
    world.mask = playfieldMask;
  }

  async function drawGround(
    width: number,
    height: number,
    opts?: { skipHexGrid?: boolean; groundUrl?: string | null },
  ) {
    clearLayer("ground_base");
    clearLayer("ground_decals");
    const bounds = mapBounds(width, height);
    setPlayfieldMask(width, height);
    const groundUrl =
      opts?.groundUrl || battle?.map?.ground_asset || "/assets/battlefield/Battlefield-MiddleEast3.png";
    try {
      // Ground tiles are photographic — load without chroma-key so dark sand/shadows stay opaque
      let gtex: Texture;
      if (textureCache.has(groundUrl)) {
        gtex = textureCache.get(groundUrl)!;
      } else {
        gtex = (await Assets.load(groundUrl)) as Texture;
        textureCache.set(groundUrl, gtex);
      }
      // Tile ground across map extents — clip each tile so it cannot spill past the playfield.
      const tile = 512;
      for (let x = bounds.minX; x < bounds.maxX; x += tile) {
        for (let y = bounds.minY; y < bounds.maxY; y += tile) {
          const spr = new Sprite(gtex);
          spr.x = x;
          spr.y = y;
          spr.width = Math.min(tile + 2, bounds.maxX - x);
          spr.height = Math.min(tile + 2, bounds.maxY - y);
          spr.alpha = 0.95;
          layers.ground_base.addChild(spr);
        }
      }
    } catch {
      const g = new Graphics()
        .rect(bounds.minX, bounds.minY, bounds.maxX - bounds.minX, bounds.maxY - bounds.minY)
        .fill({ color: 0x6b5a42 });
      layers.ground_base.addChild(g);
    }

    clearLayer("hex_grid");
    if (!opts?.skipHexGrid) {
      // Blue hex grid — drawn at full stroke; layer alpha surges dim→bright over 6s
      const grid = new Graphics();
      for (let r = 0; r < height; r++) {
        for (let q = 0; q < width; q++) {
          const p = axialToScreen(q, r);
          grid.poly(hexPoints().map((v, i) => (i % 2 === 0 ? v + p.x : v + p.y)));
          grid.stroke({ width: 1.25, color: 0x33ccff, alpha: 1 });
        }
      }
      layers.hex_grid.addChild(grid);
      pulseHexGrid();
    } else {
      layers.hex_grid.alpha = 1;
    }

    // Deploy zone washes
    const friendlyZone = new Graphics();
    const oppZone = new Graphics();
    for (let r = 45; r < 50; r++) {
      for (let q = 0; q < width; q++) {
        const p = axialToScreen(q, r);
        friendlyZone.poly(hexPoints(R * 0.9).map((v, i) => (i % 2 === 0 ? v + p.x : v + p.y)));
        friendlyZone.fill({ color: 0x2f6fed, alpha: 0.07 });
      }
    }
    for (let r = 0; r < 5; r++) {
      for (let q = 0; q < width; q++) {
        const p = axialToScreen(q, r);
        oppZone.poly(hexPoints(R * 0.9).map((v, i) => (i % 2 === 0 ? v + p.x : v + p.y)));
        oppZone.fill({ color: 0xd64545, alpha: 0.07 });
      }
    }
    layers.ground_decals.addChild(friendlyZone);
    layers.ground_decals.addChild(oppZone);
  }

  async function playGridScanIntro(width: number, height: number) {
    const preamble = !introPlaying;
    if (preamble) {
      introPlaying = true;
      gridPulseEnabled = false;
      interactable = false;
      handlers.onIntroScan?.(true);
    }

    clearLayer("hex_grid");
    clearLayer("effects_world");
    layers.hex_grid.alpha = 1;

    const bounds = mapBounds(width, height);
    // Pull camera out a bit so the flyover reads
    zoom = Math.min(zoom, 0.42);
    camera.scale.set(zoom);
    focusWorld(bounds.cx, bounds.cy);

    const hexes: { q: number; r: number; x: number; y: number }[] = [];
    for (let r = 0; r < height; r++) {
      for (let q = 0; q < width; q++) {
        const p = axialToScreen(q, r);
        hexes.push({ q, r, x: p.x, y: p.y });
      }
    }
    // Sprite faces left — fly right → left, reveal as the nose passes
    hexes.sort((a, b) => b.x - a.x || a.y - b.y);

    const revealed = new Graphics();
    layers.hex_grid.addChild(revealed);
    let nextIdx = 0;

    let drone: Sprite | null = null;
    try {
      const tex = await loadChromaTexture("/assets/fx/blue-hex-drone.png", textureCache);
      drone = new Sprite(tex);
      drone.anchor.set(0.5, 0.55);
      const targetW = R * 5.2;
      const s = targetW / Math.max(drone.texture.width, 1);
      drone.scale.set(s);
      layers.effects_world.addChild(drone);
    } catch {
      drone = null;
    }

    const lasers = new Graphics();
    layers.effects_world.addChild(lasers);

    const startX = bounds.maxX + R * 4;
    const endX = bounds.minX - R * 4;
    const flightY = bounds.minY + (bounds.maxY - bounds.minY) * 0.32;
    const DURATION_MS = 6000;
    const t0 = performance.now();
    const recentTargets: { x: number; y: number }[] = [];
    let lastLaserSfxAt = 0;
    const engineBed = playSfxBed("hex_scan_engine", 0.58);

    const strokeHex = (h: { x: number; y: number }) => {
      revealed.poly(hexPoints().map((v, i) => (i % 2 === 0 ? v + h.x : v + h.y)));
      revealed.stroke({ width: 1.35, color: 0x33ccff, alpha: 1 });
    };

    await new Promise<void>((resolve) => {
      const tick = () => {
        const raw = Math.min(1, (performance.now() - t0) / DURATION_MS);
        // ease in-out
        const t = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
        const x = startX + (endX - startX) * t;
        const y = flightY + Math.sin(raw * Math.PI * 5) * (R * 0.35);
        if (drone) {
          drone.x = x;
          drone.y = y;
        }

        // Soft engine swell as it crosses mid-map (Doppler-ish)
        if (engineBed) {
          const proximity = 1 - Math.min(1, Math.abs(0.5 - raw) * 2);
          engineBed.volume = 0.28 + proximity * 0.4;
        }

        // Reveal hexes the drone has swept past (right → left)
        const revealEdge = x + R * 0.8;
        let paintedThisFrame = 0;
        while (nextIdx < hexes.length && hexes[nextIdx].x >= revealEdge) {
          const h = hexes[nextIdx++];
          strokeHex(h);
          recentTargets.push({ x: h.x, y: h.y });
          if (recentTargets.length > 10) recentTargets.shift();
          paintedThisFrame++;
        }

        // Laser zaps — throttled so the bed stays readable
        const now = performance.now();
        if (paintedThisFrame > 0 && now - lastLaserSfxAt > 110) {
          playSfx("hex_scan_laser");
          lastLaserSfxAt = now;
        }

        lasers.clear();
        const originX = drone ? drone.x : x;
        const originY = drone ? drone.y + R * 0.35 : y + R * 0.35;
        for (let i = 0; i < recentTargets.length; i++) {
          const tgt = recentTargets[i];
          const alpha = 0.25 + (i / Math.max(recentTargets.length - 1, 1)) * 0.7;
          lasers.moveTo(originX, originY);
          lasers.lineTo(tgt.x, tgt.y);
          lasers.stroke({ width: 1.5, color: 0x66f0ff, alpha });
          lasers.circle(tgt.x, tgt.y, 3).fill({ color: 0xaaffff, alpha: alpha * 0.85 });
        }

        // Soft camera follow along the scan
        focusWorld(x * 0.55 + bounds.cx * 0.45, y * 0.25 + bounds.cy * 0.75);

        if (raw < 1) {
          requestAnimationFrame(tick);
        } else {
          resolve();
        }
      };
      requestAnimationFrame(tick);
    });

    // Ensure every hex is drawn
    while (nextIdx < hexes.length) {
      strokeHex(hexes[nextIdx++]);
    }

    stopAudio(engineBed, 220);
    lasers.destroy();
    if (drone) {
      drone.destroy();
      drone = null;
    }
    clearLayer("effects_world");

    // Fit/center after intro. Control Phase on phone overrides with commander max-zoom.
    scheduleFinishIntroFraming();
    gridSurgeElapsedMs = 0;
    gridPulseEnabled = true;
    pulseHexGrid();
    introPlaying = false;
    interactable = wantInteractable;
    handlers.onIntroScan?.(false);
    if (battle) {
      drawOverlays(battle);
      void drawUnits(battle);
    }
  }

  async function drawTerrain(terrain: any[], mapId?: string | null) {
    clearLayer("terrain_ground");
    clearLayer("terrain_structures");
    const terrainSprites = terrainSpritesForMap(mapId);
    const items = [...(terrain || [])].sort((a, b) => {
      const ay = axialToScreen(a.q, a.r).y;
      const by = axialToScreen(b.q, b.r).y;
      return ay - by || a.q - b.q;
    });

    for (const t of items) {
      const p = axialToScreen(t.q, t.r);
      const variants = terrainSprites[t.terrain_id] || [];
      if (!variants.length) {
        if (t.terrain_id === "road") {
          const g = new Graphics().poly(hexPoints(R * 0.85)).fill({ color: 0x4a463d, alpha: 0.35 });
          g.x = p.x;
          g.y = p.y;
          layers.terrain_ground.addChild(g);
        }
        continue;
      }
      const url = variants[(Math.abs(t.q * 31 + t.r * 17)) % variants.length];
      try {
        const tex = await loadChromaTexture(url, textureCache);
        const spr = new Sprite(tex);
        spr.anchor.set(0.5, 0.82);
        const draw = terrainDrawScale(mapId, t.terrain_id, url);
        const scale = terrainSpriteScaleFactor(spr.texture.width, spr.texture.height, R, draw);
        spr.scale.set(scale);
        spr.x = p.x;
        spr.y = p.y;
        // Footprint ring for readability
        const ring = new Graphics().poly(hexPoints(R * 0.7)).stroke({ width: 1.5, color: 0xffffff, alpha: 0.18 });
        ring.x = p.x;
        ring.y = p.y;
        layers.terrain_ground.addChild(ring);
        layers.terrain_structures.addChild(spr);
      } catch {
        const g = new Graphics().poly(hexPoints()).fill({ color: 0x7a6850, alpha: 0.7 });
        g.x = p.x;
        g.y = p.y;
        layers.terrain_structures.addChild(g);
      }
    }
  }

  function drawOverlays(next: any) {
    clearLayer("hex_overlays");
    const opts = next.legal_player_options || [];
    const reachable = next.reachable_hexes || [];
    const seenMove = new Set<string>();

    const cp = next.control_phase;
    if (cp?.active && cp.side === "friendly" && !introPlaying) {
      const mapW = Number(next.map?.width || 50);
      const mapH = Number(next.map?.height || 50);
      const shade = new Graphics()
        .rect(-R * 4, -R * 4, mapW * R * SQRT3 + R * 8, mapH * R * 1.55 + R * 8)
        .fill({ color: 0x07101c, alpha: 0.52 });
      layers.hex_overlays.addChild(shade);
    }

    // Smoke fog overlays
    for (const fx of next.field_effects || []) {
      if (fx.effect_type !== "smoke") continue;
      const cq = Number(fx.center?.q ?? 0);
      const cr = Number(fx.center?.r ?? 0);
      const rad = Number(fx.radius ?? 2);
      for (let dq = -rad; dq <= rad; dq++) {
        for (let dr = -rad; dr <= rad; dr++) {
          const q = cq + dq;
          const r = cr + dr;
          if (hexDistance(cq, cr, q, r) > rad) continue;
          const p = axialToScreen(q, r);
          const g = new Graphics().poly(hexPoints(R * 0.92)).fill({ color: 0x8899aa, alpha: 0.38 });
          g.stroke({ width: 1, color: 0xbcc8d4, alpha: 0.35 });
          g.x = p.x;
          g.y = p.y;
          layers.hex_overlays.addChild(g);
        }
      }
    }

    // Mines visible to the player (own always; enemy only if revealed)
    for (const mine of next.mines || []) {
      const q = Number(mine.position?.q);
      const r = Number(mine.position?.r);
      if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
      const p = axialToScreen(q, r);
      const enemy = mine.side === "opposition";
      const color = enemy ? 0xd64545 : 0xc9a227;
      const g = new Graphics()
        .circle(0, 0, R * 0.28)
        .fill({ color, alpha: mine.hidden_from_enemy ? 0.55 : 0.8 });
      g.stroke({ width: 2, color: 0x111111, alpha: 0.9 });
      g.x = p.x;
      g.y = p.y;
      layers.hex_overlays.addChild(g);
      const spike = new Graphics().poly([-4, -10, 4, -10, 0, 8]).fill({ color: 0x222222, alpha: 0.95 });
      spike.x = p.x;
      spike.y = p.y;
      layers.hex_overlays.addChild(spike);
    }

    // Spoof / ability placement: clickable hexes within signal (not move range)
    if (placementHexes && placementHexes.length) {
      for (const h of placementHexes) {
        const key = `${h.q},${h.r}`;
        if (seenMove.has(key)) continue;
        seenMove.add(key);
        const p = axialToScreen(h.q, h.r);
        const g = new Graphics().poly(hexPoints(R * 0.88)).fill({ color: 0x33ddee, alpha: 0.2 });
        g.stroke({ width: 1.5, color: 0x66f0ff, alpha: 0.9 });
        g.x = p.x;
        g.y = p.y;
        if (interactable) {
          g.eventMode = "static";
          g.cursor = "pointer";
          g.on("pointertap", (e) => {
            e.stopPropagation();
            if (!interactable) return;
            handlers.onHexSelected?.({ q: h.q, r: h.r });
          });
        }
        layers.hex_overlays.addChild(g);
      }
    } else {
      // Green highlight for all reachable move hexes (player Speed range)
      for (const h of reachable) {
        const key = `${h.q},${h.r}`;
        if (seenMove.has(key)) continue;
        seenMove.add(key);
        const p = axialToScreen(h.q, h.r);
        const g = new Graphics().poly(hexPoints(R * 0.88)).fill({ color: 0x33aa66, alpha: 0.16 });
        g.stroke({ width: 1.5, color: 0x5fd68a, alpha: 0.75 });
        g.x = p.x;
        g.y = p.y;
        if (interactable) {
          g.eventMode = "static";
          g.cursor = "pointer";
          g.on("pointertap", (e) => {
            e.stopPropagation();
            if (!interactable) return;
            handlers.onHexSelected?.({ q: h.q, r: h.r });
          });
        }
        layers.hex_overlays.addChild(g);
      }
    }

    for (const opt of opts) {
      if (opt.subroutine === "attack") {
        for (const h of opt.preview?.affected_hexes || []) {
          const p = axialToScreen(h.q, h.r);
          const g = new Graphics();
          g.rect(-16, -16, 32, 32).stroke({ width: 2, color: 0xff3344, alpha: 0.95 });
          g.moveTo(-10, 0).lineTo(10, 0).stroke({ width: 2, color: 0xff3344 });
          g.moveTo(0, -10).lineTo(0, 10).stroke({ width: 2, color: 0xff3344 });
          g.x = p.x;
          g.y = p.y - 8;
          layers.hex_overlays.addChild(g);
        }
      }
    }

    if (next.commander?.position && next.signal_radius) {
      const cp = axialToScreen(next.commander.position.q, next.commander.position.r);
      const radiusPx = next.signal_radius * R * SQRT3 * 0.75;
      const sig = new Graphics().circle(0, 0, radiusPx).stroke({ width: 2, color: 0x33ddee, alpha: 0.45 });
      // radio ticks
      for (let i = 0; i < 8; i++) {
        const a = (Math.PI * 2 * i) / 8;
        sig.moveTo(Math.cos(a) * (radiusPx - 6), Math.sin(a) * (radiusPx - 6));
        sig.lineTo(Math.cos(a) * (radiusPx + 6), Math.sin(a) * (radiusPx + 6));
        sig.stroke({ width: 2, color: 0x33ddee, alpha: 0.5 });
      }
      sig.x = cp.x;
      sig.y = cp.y;
      layers.hex_overlays.addChild(sig);
    }
  }

  async function drawUnits(next: any) {
    if (moveAnimating) return;
    const gen = ++unitsDrawGen;
    // Build off-layer first so an abort never wipes the live board mid-move
    const built: Container[] = [];
    const allUnits = [...(next.friendly_units || []), ...(next.opposition_units || [])];

    type DrawItem = {
      unit: any;
      modelId: string | null;
      q: number;
      r: number;
      isLeader: boolean;
    };
    const items: DrawItem[] = [];
    for (const u of allUnits) {
      if (!u.alive) continue;
      const living = (u.models || []).filter((m: any) => m.alive && m.position);
      if (u.category === "soldier_squad" && living.length) {
        const leaderId = u.leader_model_id || living[living.length - 1]?.model_id;
        for (const m of living) {
          items.push({
            unit: u,
            modelId: m.model_id,
            q: m.position.q,
            r: m.position.r,
            isLeader: m.model_id === leaderId,
          });
        }
      } else {
        items.push({
          unit: u,
          modelId: living[0]?.model_id || "m1",
          q: u.position.q,
          r: u.position.r,
          isLeader: true,
        });
      }
    }

    items.sort((a, b) => {
      const ay = axialToScreen(a.q, a.r).y;
      const by = axialToScreen(b.q, b.r).y;
      return ay - by || a.q - b.q || String(a.modelId).localeCompare(String(b.modelId));
    });

    const ramBadgePlans: Array<{
      x: number;
      y: number;
      count: number;
      source: "commander" | "drone";
      unitId: string;
    }> = [];

    for (const item of items) {
      if (gen !== unitsDrawGen || moveAnimating) {
        for (const c of built) c.destroy({ children: true });
        return;
      }
      const u = item.unit;
      const p = axialToScreen(item.q, item.r);
      const container = new Container();
      container.x = p.x;
      container.y = p.y;
      (container as any).unitId = u.unit_instance_id;
      (container as any).modelId = item.modelId;
      (container as any).hexQ = item.q;
      (container as any).hexR = item.r;
      container.eventMode = "static";
      container.cursor = "pointer";
      container.on("pointertap", (e) => {
        e.stopPropagation();
        handlers.onUnitSelected?.(u.unit_instance_id);
      });

      const isDecoy = !!u.is_decoy || u.category === "decoy";
      const baseColor = u.side === "friendly" ? 0x2f6fed : 0xc23b3b;
      const ellipseScale = u.category === "soldier_squad" ? 0.42 : 0.55;
      const base = new Graphics()
        .ellipse(0, 8, R * ellipseScale, R * ellipseScale * 0.5)
        .fill({ color: baseColor, alpha: isDecoy ? 0.25 : 0.5 });
      base.stroke({ width: isDecoy ? 2 : 1.25, color: isDecoy ? 0x88ccff : 0xffffff, alpha: isDecoy ? 0.85 : 0.3 });
      if (isDecoy) {
        const ring = new Graphics().ellipse(0, 8, R * 0.62, R * 0.34).stroke({ width: 1, color: 0x88ccff, alpha: 0.7 });
        container.addChild(ring);
        container.alpha = 0.75;
      }
      container.addChild(base);

      const isActive = u.unit_instance_id === next.active_actor_id;
      const isSelected = u.unit_instance_id === selectedId;
      if ((isActive || isSelected) && item.isLeader) {
        const ring = new Graphics()
          .ellipse(0, 8, R * 0.7, R * 0.36)
          .stroke({ width: 2.5, color: isActive ? 0xffcc33 : 0xffffff, alpha: 0.95 });
        container.addChild(ring);
      }

      const cp = next.control_phase;
      const eligibleIds = new Set<string>(cp?.eligible_drone_ids || []);
      const isCp = !!(cp?.active && cp.side === "friendly" && !introPlaying);
      const isCpHighlight =
        isCp &&
        (u.unit_instance_id === cp.commander_id || eligibleIds.has(u.unit_instance_id));
      if (isCp && item.isLeader) {
        if (isCpHighlight) {
          // Bright allocation target: soft fill + double ring so eligible units pop through the dim
          const soft = new Graphics()
            .ellipse(0, 8, R * 1.05, R * 0.55)
            .fill({ color: 0x3aa0ff, alpha: 0.28 });
          const outer = new Graphics()
            .ellipse(0, 8, R * 1.12, R * 0.58)
            .stroke({ width: 5, color: 0x66ccff, alpha: 1 });
          const inner = new Graphics()
            .ellipse(0, 8, R * 0.88, R * 0.46)
            .stroke({ width: 2.5, color: 0xffffff, alpha: 0.95 });
          container.addChild(soft);
          container.addChild(outer);
          container.addChild(inner);
          container.alpha = 1;
        } else {
          container.alpha = 0.28;
        }
      }

      try {
        const tex = await loadChromaTexture(unitReadyUrl(u, next.commander_avatar), textureCache);
        if (gen !== unitsDrawGen || moveAnimating) {
          container.destroy({ children: true });
          for (const c of built) c.destroy({ children: true });
          return;
        }
        const spr = new Sprite(tex);
        spr.anchor.set(0.5, 0.92);
        (spr as any).role = "ready";
        const h = unitSpriteTargetHeight(R, {
          category: u.category,
          sizeClass: u.size_class,
          assetSetId: u.asset_set_id,
          side: u.side,
          definitionId: u.definition_id,
        });
        const sc = h / Math.max(spr.texture.height, 1);
        const faceKey = item.modelId ? modelKey(u.unit_instance_id, String(item.modelId)) : u.unit_instance_id;
        const face = facingByUnit.get(faceKey) ?? facingFor(u.unit_instance_id, u.side);
        const artFace = unitArtFace(u.asset_set_id, u.category, next.commander_avatar, u.definition_id);
        spr.scale.set(sc * face * artFace, sc);
        container.addChild(spr);
      } catch {
        if (gen !== unitsDrawGen || moveAnimating) {
          container.destroy({ children: true });
          for (const c of built) c.destroy({ children: true });
          return;
        }
        const g = new Graphics().circle(0, -6, u.category === "soldier_squad" ? 10 : 14).fill({ color: baseColor });
        (g as any).role = "ready";
        container.addChild(g);
      }

      if (item.isLeader) {
        const label = new Text({
          text: shortName(u),
          style: {
            fill: 0xffffff,
            fontSize: 11,
            fontWeight: "700",
            stroke: { color: 0x000000, width: 3 },
          },
        });
        label.anchor.set(0.5, 0);
        label.y = 16;
        container.addChild(label);

        if (u.living_model_count != null && u.model_count > 1) {
          const hp = new Text({
            text: `${u.living_model_count}/${u.model_count}`,
            style: { fill: 0xffe08a, fontSize: 10, stroke: { color: 0x000000, width: 3 } },
          });
          hp.anchor.set(0.5, 0);
          hp.y = 28;
          container.addChild(hp);
        }

        if (Array.isArray(u.statuses) && u.statuses.includes("painted")) {
          const paintRing = new Graphics()
            .circle(0, -6, R * 0.72)
            .stroke({ width: 3, color: 0xff8800, alpha: 0.95 });
          container.addChild(paintRing);
        }
      }

      // RAM icons drawn on a top layer after all units (so they are never buried under neighboring art).
      if (item.isLeader) {
        let ramCount = 0;
        let ramSource: "commander" | "drone" | null = null;
        if (u.category === "commander") {
          ramCount = Math.max(0, Number(u.ram_current || 0));
          ramSource = "commander";
        } else if (Number(u.allocated_ram || 0) > 0) {
          ramCount = Math.max(0, Number(u.allocated_ram || 0));
          ramSource = "drone";
        }
        if (ramCount > 0 && ramSource) {
          ramBadgePlans.push({
            x: p.x,
            y: p.y,
            count: ramCount,
            source: ramSource,
            unitId: u.unit_instance_id,
          });
        }
      }

      built.push(container);
    }

    if (gen !== unitsDrawGen || moveAnimating) {
      for (const c of built) c.destroy({ children: true });
      return;
    }

    // Atomic swap onto the live layer
    clearLayer("units");
    clearLayer("ram_badges");
    clearLayer("objectives_and_labels");
    for (const container of built) {
      layers.units.addChild(container);
      const uid = (container as any).unitId;
      const mid = (container as any).modelId;
      if (uid && mid) modelRegistry.set(modelKey(String(uid), String(mid)), container);
    }

    // Sticky RAM badges — always above unit sprites
    if (ramBadgePlans.length) {
      try {
        let ramTex = textureCache.get(RAM_ICON_URL);
        if (!ramTex) {
          ramTex = (await Assets.load(RAM_ICON_URL)) as Texture;
          textureCache.set(RAM_ICON_URL, ramTex);
        }
        if (ramTex && gen === unitsDrawGen && !moveAnimating) {
          const iconSize = isPhoneViewport()
            ? Math.max(20, Math.round(R * 0.78))
            : Math.max(14, Math.round(R * 0.58));
          const cpActive = !!(next.control_phase?.active && next.control_phase.side === "friendly" && !introPlaying);
          for (const plan of ramBadgePlans) {
            const rowY = plan.y + 14;
            const startX = plan.x - R * 0.95;
            for (let i = 0; i < plan.count; i++) {
              const badge = new Container();
              badge.x = startX + i * (iconSize * 0.78);
              badge.y = rowY;
              const glow = new Graphics()
                .circle(0, 0, iconSize * 0.62)
                .fill({ color: 0x66e0ff, alpha: 0.45 });
              const glowOuter = new Graphics()
                .circle(0, 0, iconSize * 0.82)
                .fill({ color: 0x2a8cff, alpha: 0.22 });
              badge.addChild(glowOuter);
              badge.addChild(glow);
              const icon = new Sprite(ramTex);
              icon.width = iconSize;
              icon.height = iconSize;
              icon.anchor.set(0.5, 0.5);
              (icon as any).role = "ram_icon";
              badge.addChild(icon);
              if (cpActive) {
                badge.eventMode = "static";
                badge.cursor = "grab";
                const source = plan.source;
                const droneId = plan.unitId;
                const texForGhost = ramTex;
                badge.on("pointerdown", (e) => {
                  e.stopPropagation();
                  if (ramDrag) return;
                  const ghost = new Sprite(texForGhost);
                  ghost.width = iconSize;
                  ghost.height = iconSize;
                  ghost.anchor.set(0.5, 0.5);
                  ghost.alpha = 0.9;
                  const gp = e.global;
                  const local = world.toLocal(gp);
                  ghost.x = local.x;
                  ghost.y = local.y;
                  layers.battlefield_hud.addChild(ghost);
                  ramDrag = {
                    from: source,
                    droneId: source === "drone" ? droneId : undefined,
                    ghost,
                  };
                });
              }
              layers.ram_badges.addChild(badge);
            }
          }
        }
      } catch {
        /* icon optional */
      }
    }

    // Objective zones + flags
    const zones = Array.isArray(next.objective?.zones) ? next.objective.zones : [];
    const flags = Array.isArray(next.objective?.flags) ? next.objective.flags : [];
    const vpF = next.objective?.friendly_vp ?? 0;
    const vpO = next.objective?.opposition_vp ?? 0;
    const vpW = next.objective?.vp_to_win ?? 5;
    const objTitle = String(next.objective?.label || "OBJECTIVE").toUpperCase();

    const zoneColor = (control: string) =>
      control === "friendly" ? 0x4aa3ff : control === "opposition" ? 0xff6655 : control === "contested" ? 0xffcc33 : 0xd4a017;

    for (const zone of zones.length ? zones : [{ hex: next.objective?.hex, radius: 5, control: next.objective?.control || "empty", label: "" }]) {
      const oq = Number(zone.hex?.q ?? Math.floor((next.map?.width || 50) / 2));
      const or_ = Number(zone.hex?.r ?? Math.floor((next.map?.height || 50) / 2));
      const radius = Number(zone.radius ?? 5);
      const obj = axialToScreen(oq, or_);
      // Ring radius: one hex step east on the same row (brick horizontal pitch)
      const ringEdge = axialToScreen(oq + radius, or_);
      const rx = Math.max(80, Math.abs(ringEdge.x - obj.x));
      const ry = rx * ISO_Y_SCALE;
      const control = String(zone.control || "empty");
      const ringColor = zoneColor(control);
      const ring = new Graphics().ellipse(0, 0, rx, ry).stroke({ width: 3, color: ringColor, alpha: 0.55 });
      ring.x = obj.x;
      ring.y = obj.y;
      const marker = new Graphics()
        .poly([0, -14, 10, 0, 0, 14, -10, 0])
        .fill({ color: ringColor, alpha: 0.95 });
      marker.x = obj.x;
      marker.y = obj.y;
      layers.objectives_and_labels.addChild(ring);
      layers.objectives_and_labels.addChild(marker);
    }

    for (const flag of flags) {
      const fq = Number(flag.hex?.q ?? flag.spawn_hex?.q ?? 0);
      const fr = Number(flag.hex?.r ?? flag.spawn_hex?.r ?? 0);
      const pos = axialToScreen(fq, fr);
      const held = !!flag.holder_unit_id;
      const side = String(flag.side || "");
      const flagColor = side === "friendly" ? 0x4aa3ff : side === "opposition" ? 0xff6655 : 0xffffff;
      const pole = new Graphics()
        .rect(-1, -18, 2, 22)
        .fill({ color: 0xdddddd, alpha: 0.95 });
      pole.x = pos.x;
      pole.y = pos.y;
      const banner = new Graphics()
        .poly([2, -16, 14, -12, 2, -8])
        .fill({ color: flagColor, alpha: held ? 0.95 : 0.65 });
      banner.x = pos.x;
      banner.y = pos.y;
      layers.objectives_and_labels.addChild(pole);
      layers.objectives_and_labels.addChild(banner);
    }

    const primaryHex = zones[0]?.hex || next.objective?.hex;
    const primary = axialToScreen(Number(primaryHex?.q ?? 25), Number(primaryHex?.r ?? 25));
    const objLabel = new Text({
      text: `${objTitle} ${vpF}–${vpO}/${vpW}`,
      style: { fill: 0xffe08a, fontSize: 12, fontWeight: "700", stroke: { color: 0x000000, width: 3 } },
    });
    objLabel.anchor.set(0.5, 0);
    objLabel.x = primary.x;
    objLabel.y = primary.y + 16;
    layers.objectives_and_labels.addChild(objLabel);
  }

  async function hydrate(next: any) {
    // Keep latest battle pointer, but don't rebuild mid-scan / mid-move (would revive ready ghosts)
    if (introPlaying || moveAnimating) {
      battle = next;
      return;
    }
    const prevId = battle?.battle_id;
    const mapChanged = !battle || battle.map?.map_id !== next.map?.map_id || prevId !== next.battle_id;
    const activeChanged = next.active_actor_id && next.active_actor_id !== lastActiveId;
    const battleId = String(next.battle_id || "");
    const shouldIntro = mapChanged && !!battleId && introPlayedBattleId !== battleId;
    battle = next;
    if (mapChanged) {
      facingByUnit.clear();
      const w = next.map?.width || 50;
      const h = next.map?.height || 50;
      handlers.onLoadProgress?.(22);
      await drawGround(w, h, {
        skipHexGrid: shouldIntro,
        groundUrl: next.map?.ground_asset,
      });
      handlers.onLoadProgress?.(48);
      await drawTerrain(next.map?.terrain || [], next.map?.map_id);
      handlers.onLoadProgress?.(72);
      didInitialFrame = false;
    }
    if (shouldIntro && !introPlaying) {
      introPlaying = true;
      gridPulseEnabled = false;
      interactable = false;
      handlers.onIntroScan?.(true);
    }
    drawOverlays(next);
    await drawUnits(next);
    if (mapChanged) {
      handlers.onLoadProgress?.(100);
      handlers.onAssetsReady?.();
    }
    if (shouldIntro) {
      introPlayedBattleId = battleId;
      await playGridScanIntro(next.map?.width || 50, next.map?.height || 50);
      didInitialFrame = true;
    } else if (!didInitialFrame) {
      scheduleCenterOnMap();
      didInitialFrame = true;
    } else if (activeChanged && !mapLocked) {
      centerOnActive();
    }
    lastActiveId = next.active_actor_id || null;
  }

  // Pan / zoom — overview stays locked edge-to-edge; pan only when zoomed in.
  let dragging = false;
  let last = { x: 0, y: 0 };
  let lastHostW = 0;
  let lastHostH = 0;
  const activePointers = new Map<number, { x: number; y: number }>();
  let pinchState: {
    dist: number;
    zoom: number;
    midX: number;
    midY: number;
    worldX: number;
    worldY: number;
  } | null = null;

  function canvasPoint(e: { clientX: number; clientY: number }) {
    const rect = app.canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function applyZoomAtScreen(midX: number, midY: number, nextZoom: number) {
    refreshOverviewFloor();
    const maxZ = Math.max(MAX_ZOOM, overviewZoom * 3);
    const worldX = (midX - camera.x) / zoom;
    const worldY = (midY - camera.y) / zoom;
    if (nextZoom <= overviewZoom * 1.001) {
      centerOnMap({ fit: true, mode: "contain", lock: true });
      return;
    }
    zoom = Math.min(maxZ, Math.max(overviewZoom || 0.05, nextZoom));
    mapLocked = false;
    camera.scale.set(zoom);
    camera.x = midX - worldX * zoom;
    camera.y = midY - worldY * zoom;
    clampCameraToMap();
  }

  function clearPointer(id: number) {
    activePointers.delete(id);
    if (activePointers.size < 2) pinchState = null;
    if (activePointers.size === 0) dragging = false;
  }
  const resizeObserver = new ResizeObserver(() => {
    const { w, h } = viewportSize();
    if (w < 32 || h < 32) return;
    const sizeChanged = Math.abs(w - lastHostW) > 1 || Math.abs(h - lastHostH) > 1;
    if (!sizeChanged) return;
    lastHostW = w;
    lastHostH = h;
    // Refresh overview baseline, but do NOT yank the player back to full zoom-out
    // on every HUD reflow (move/RAM panels used to trigger that).
    const overview = computeContainZoom();
    if (overview != null) overviewZoom = overview;
    if (mapLocked) {
      // Locked means full-board overview — stay on contain, not phone mid.
      centerOnMap({ fit: true, mode: "contain", lock: true });
    } else {
      if (zoom < overviewZoom) {
        zoom = overviewZoom;
        camera.scale.set(zoom);
      }
      clampCameraToMap();
    }
  });
  resizeObserver.observe(host);

  app.canvas.addEventListener("pointerdown", (e) => {
    const pt = canvasPoint(e);
    activePointers.set(e.pointerId, pt);
    try {
      app.canvas.setPointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }

    if (activePointers.size === 2) {
      dragging = false;
      const pts = [...activePointers.values()];
      const dist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
      const midX = (pts[0].x + pts[1].x) / 2;
      const midY = (pts[0].y + pts[1].y) / 2;
      pinchState = {
        dist: Math.max(dist, 8),
        zoom,
        midX,
        midY,
        worldX: (midX - camera.x) / zoom,
        worldY: (midY - camera.y) / zoom,
      };
      return;
    }

    // Pan whenever the board is larger than the view (phone mid crops the map).
    if (mapLocked) return;
    if (!battle) return;
    const b = mapBounds(battle.map?.width || 50, battle.map?.height || 50);
    const { w, h } = viewportSize();
    const mapW = (b.maxX - b.minX) * zoom;
    const mapH = (b.maxY - b.minY) * zoom;
    if (mapW <= w + 1 && mapH <= h + 1) return;
    if (e.button === 1 || e.button === 0) {
      dragging = true;
      last = { x: e.clientX, y: e.clientY };
    }
  });
  const onPointerUp = (e: PointerEvent) => {
    clearPointer(e.pointerId);
    try {
      if (app.canvas.hasPointerCapture(e.pointerId)) app.canvas.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    if (!ramDrag) return;
    const ghost = ramDrag.ghost;
    const from = ramDrag.from;
    const fromDroneId = ramDrag.droneId;
    ramDrag = null;
    ghost.destroy();
    if (!battle?.control_phase?.active) return;
    const rect = app.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const wx = (sx - camera.x) / zoom;
    const wy = (sy - camera.y) / zoom;
    let bestId: string | null = null;
    let bestDist = R * 1.35;
    for (const child of layers.units.children) {
      const c = child as Container;
      const uid = String((c as any).unitId || "");
      if (!uid) continue;
      const dx = c.x - wx;
      const dy = c.y - wy;
      const d = Math.hypot(dx, dy);
      if (d < bestDist) {
        bestDist = d;
        bestId = uid;
      }
    }
    if (!bestId) return;
    const cp = battle.control_phase;
    const eligible = new Set<string>(cp.eligible_drone_ids || []);
    if (from === "commander" && eligible.has(bestId)) {
      handlers.onRamAllocate?.(bestId);
    } else if (from === "drone" && fromDroneId && bestId === cp.commander_id) {
      handlers.onRamReclaim?.(fromDroneId);
    }
  };
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
  window.addEventListener("pointermove", (e) => {
    const pt = canvasPoint(e);
    if (activePointers.has(e.pointerId)) activePointers.set(e.pointerId, pt);

    if (activePointers.size === 2 && pinchState) {
      const pts = [...activePointers.values()];
      const dist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
      const midX = (pts[0].x + pts[1].x) / 2;
      const midY = (pts[0].y + pts[1].y) / 2;
      const scale = dist / Math.max(pinchState.dist, 8);
      applyZoomAtScreen(midX, midY, pinchState.zoom * scale);
      return;
    }

    if (ramDrag) {
      const rect = app.canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      ramDrag.ghost.x = (sx - camera.x) / zoom;
      ramDrag.ghost.y = (sy - camera.y) / zoom;
      return;
    }
    if (!dragging || mapLocked) return;
    camera.x += e.clientX - last.x;
    camera.y += e.clientY - last.y;
    last = { x: e.clientX, y: e.clientY };
    clampCameraToMap();
  });
  app.canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      zoomBy(e.deltaY > 0 ? 0.9 : 1.1);
    },
    { passive: false }
  );

  return {
    destroy: () => {
      resizeObserver.disconnect();
      app.ticker.remove(onGridTicker);
      app.destroy(true);
      host.innerHTML = "";
      textureCache.clear();
    },
    hydrate,
    setSelection: (id) => {
      selectedId = id;
      if (battle) void hydrate(battle);
    },
    setInteractable: (ok) => {
      wantInteractable = ok;
      interactable = ok && !introPlaying;
      if (battle && !introPlaying) drawOverlays(battle);
    },
    setPlacementHexes: (hexes) => {
      placementHexes = hexes && hexes.length ? hexes.map((h) => ({ q: h.q, r: h.r })) : null;
      if (battle) drawOverlays(battle);
    },
    centerOnActive,
    centerOnMap: () => {
      // Map button = full-board overview (zoom all the way out).
      centerOnMap({ fit: true, mode: "contain", lock: true });
    },
    centerOnUnit,
    ensurePlayZoom,
    zoomToMaxOnUnit,
    zoomBy,
    playMoveAnimation,
    playAttackFlash,
    playSquadVolley,
    playDeployMine,
    playCombatFx,
  };
}

function shortName(u: any): string {
  if (u.category === "commander") return "CMDR";
  const parts = String(u.display_name || "").split(" ");
  return parts[0].slice(0, 8);
}
