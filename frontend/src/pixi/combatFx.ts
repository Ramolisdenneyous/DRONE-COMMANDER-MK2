import { Assets, Container, Graphics, Sprite, Texture } from "pixi.js";

export type CombatFxKind = "gunfire" | "explosion_small" | "explosion_large";
export type Hex = { q: number; r: number };

const HIT_MS = 140;
const EXPLOSION_SMALL_MS = 520;
const EXPLOSION_LARGE_MS = 720;
const TRACER_MS = 90;
const VOLLEY_STAGGER_MS = 38;
const VOLLEY_CAP_MS = 520;

const AOE_BLAST_FRAME_COUNT = 16;
const AOE_BLAST_URLS = Array.from(
  { length: AOE_BLAST_FRAME_COUNT },
  (_, i) => `/assets/fx/aoe-blast/frame_${String(i).padStart(3, "0")}.png`,
);

let aoeBlastFrames: Texture[] | null = null;
let aoeBlastLoad: Promise<Texture[]> | null = null;

async function loadAoeBlastFrames(): Promise<Texture[]> {
  if (aoeBlastFrames?.length) return aoeBlastFrames;
  if (!aoeBlastLoad) {
    aoeBlastLoad = Promise.all(AOE_BLAST_URLS.map((url) => Assets.load(url) as Promise<Texture>))
      .then((frames) => {
        aoeBlastFrames = frames;
        return frames;
      })
      .catch((err) => {
        aoeBlastLoad = null;
        throw err;
      });
  }
  return aoeBlastLoad;
}

function easeOut(t: number) {
  return 1 - (1 - t) * (1 - t);
}

function runAnim(ms: number, tick: (t: number) => void): Promise<void> {
  return new Promise((resolve) => {
    const t0 = performance.now();
    const step = () => {
      const t = Math.min(1, (performance.now() - t0) / ms);
      tick(t);
      if (t < 1) requestAnimationFrame(step);
      else resolve();
    };
    requestAnimationFrame(step);
  });
}

function sparkBurst(g: Graphics, cx: number, cy: number, radius: number, alpha: number, color: number) {
  const n = 7;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 + 0.3;
    const x2 = cx + Math.cos(a) * radius;
    const y2 = cy + Math.sin(a) * radius * 0.72;
    g.moveTo(cx, cy).lineTo(x2, y2).stroke({ width: 1.6, color, alpha });
  }
}

export function flashUnitSprite(container: Container, ms = HIT_MS): Promise<void> {
  const ready = container.children.find((c) => (c as any).role === "ready") as Sprite | Graphics | undefined;
  const overlay = new Graphics().circle(0, -10, 16).fill({ color: 0xffffff, alpha: 0.85 });
  (overlay as any).role = "hit_flash";
  container.addChild(overlay);
  const prevTint = ready instanceof Sprite ? ready.tint : null;
  if (ready instanceof Sprite) ready.tint = 0xffffff;
  return runAnim(ms, (t) => {
    const fade = 1 - t;
    overlay.alpha = fade * 0.9;
    overlay.scale.set(1 + t * 0.55);
    if (ready instanceof Sprite) {
      const mix = fade;
      const r = 0xff;
      const g = 0xe0 + Math.floor((0xff - 0xe0) * mix);
      const b = 0xb0 + Math.floor((0xff - 0xb0) * mix);
      ready.tint = (r << 16) + (g << 8) + b;
    }
  }).then(() => {
    overlay.destroy();
    if (ready instanceof Sprite && prevTint != null) ready.tint = prevTint;
  });
}

function drawGunHit(g: Graphics, x: number, y: number, t: number) {
  g.clear();
  const k = easeOut(t);
  const alpha = 1 - t;
  g.circle(x, y, 4 + k * 10).fill({ color: 0xfff4c2, alpha: alpha * 0.85 });
  g.circle(x, y, 7 + k * 16).stroke({ width: 2, color: 0xffcc44, alpha: alpha * 0.95 });
  sparkBurst(g, x, y, 10 + k * 14, alpha, 0xffee88);
}

function drawExplosion(g: Graphics, x: number, y: number, t: number, scale: number) {
  g.clear();
  const k = easeOut(t);
  const alpha = 1 - t * 0.92;
  const core = 8 * scale + k * 18 * scale;
  g.circle(x, y, core * 1.7).fill({ color: 0xff3311, alpha: alpha * 0.35 });
  g.circle(x, y, core).fill({ color: 0xffaa33, alpha: alpha * 0.9 });
  g.circle(x, y, core * 0.45).fill({ color: 0xfff6d0, alpha: alpha });
  g.circle(x, y, 12 * scale + k * 28 * scale).stroke({ width: 3, color: 0xff6622, alpha: alpha * 0.85 });
  g.circle(x, y, 18 * scale + k * 36 * scale).stroke({ width: 1.5, color: 0xffcc66, alpha: alpha * 0.55 });
  sparkBurst(g, x, y, 16 * scale + k * 22 * scale, alpha, 0xffdd77);
}

export async function playHitBurst(layer: Container, x: number, y: number): Promise<void> {
  const g = new Graphics();
  layer.addChild(g);
  await runAnim(HIT_MS, (t) => drawGunHit(g, x, y, t));
  g.destroy();
}

/** Prefetch AOE blast frames so the first detonation does not hitch. */
export function preloadAoeBlast(): void {
  void loadAoeBlastFrames().catch(() => undefined);
}

async function playAoeBlastSprite(
  layer: Container,
  x: number,
  y: number,
  kind: "explosion_small" | "explosion_large",
): Promise<boolean> {
  let frames: Texture[];
  try {
    frames = await loadAoeBlastFrames();
  } catch {
    return false;
  }
  if (!frames.length) return false;

  const spr = new Sprite(frames[0]);
  spr.anchor.set(0.5, 0.55);
  const targetW = kind === "explosion_large" ? 118 : 78;
  const sc = targetW / Math.max(frames[0].width, 1);
  spr.scale.set(sc);
  spr.x = x;
  spr.y = y;
  spr.zIndex = 50;
  layer.addChild(spr);

  const ms = kind === "explosion_large" ? EXPLOSION_LARGE_MS : EXPLOSION_SMALL_MS;
  await runAnim(ms, (t) => {
    const idx = Math.min(frames.length - 1, Math.floor(t * frames.length));
    spr.texture = frames[idx];
    // Slight expand + soft fade on the last third
    const grow = 1 + t * 0.18;
    spr.scale.set(sc * grow);
    spr.alpha = t > 0.72 ? 1 - (t - 0.72) / 0.28 : 1;
  });
  spr.destroy();
  return true;
}

export async function playExplosionBurst(
  layer: Container,
  x: number,
  y: number,
  kind: "explosion_small" | "explosion_large",
): Promise<void> {
  const usedSprite = await playAoeBlastSprite(layer, x, y, kind);
  if (usedSprite) return;
  const g = new Graphics();
  layer.addChild(g);
  const scale = kind === "explosion_large" ? 2.15 : 1.15;
  const ms = kind === "explosion_large" ? EXPLOSION_LARGE_MS : EXPLOSION_SMALL_MS;
  await runAnim(ms, (t) => drawExplosion(g, x, y, t, scale));
  g.destroy();
}

export async function playTracer(layer: Container, ax: number, ay: number, bx: number, by: number, color = 0xff5533): Promise<void> {
  const g = new Graphics();
  layer.addChild(g);
  await runAnim(TRACER_MS, (t) => {
    g.clear();
    const fade = 1 - t * 0.4;
    g.moveTo(ax, ay).lineTo(bx, by).stroke({ width: 2.4, color, alpha: fade });
    g.circle(bx, by, 3 + t * 5).fill({ color: 0xffe08a, alpha: fade });
  });
  g.destroy();
}

export function combatFxDuration(kind: CombatFxKind, shotCount: number): number {
  if (kind !== "gunfire") {
    return kind === "explosion_large" ? EXPLOSION_LARGE_MS : EXPLOSION_SMALL_MS;
  }
  if (shotCount <= 1) return TRACER_MS + HIT_MS * 0.35;
  const last = Math.min(VOLLEY_CAP_MS - HIT_MS, (shotCount - 1) * VOLLEY_STAGGER_MS);
  return Math.min(VOLLEY_CAP_MS, last + HIT_MS);
}

export { HIT_MS, EXPLOSION_SMALL_MS, EXPLOSION_LARGE_MS, TRACER_MS, VOLLEY_STAGGER_MS, VOLLEY_CAP_MS };
