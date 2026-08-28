/** Battle soundtrack bed. Music stays at 50%; SFX are a separate mixer. */

import { unlockSfx } from "./sfx";

const TRACKS = ["/assets/music/Iron-Mesa-part1.mp3", "/assets/music/Iron-Mesa-part2.mp3"];
const MUSIC_VOLUME = 0.25;
const FADE_MS = 700;

let current: HTMLAudioElement | null = null;
let trackIndex = 0;
let started = false;
let fadedOut = false;

function fadeTo(a: HTMLAudioElement, to: number, ms: number, then?: () => void): void {
  const from = a.volume;
  const t0 = performance.now();
  const tick = () => {
    if (a !== current && to > 0) return;
    const t = Math.min(1, (performance.now() - t0) / ms);
    a.volume = Math.max(0, Math.min(1, from + (to - from) * t));
    if (t < 1) requestAnimationFrame(tick);
    else then?.();
  };
  requestAnimationFrame(tick);
}

function playIndex(i: number): void {
  if (!started || fadedOut) return;
  trackIndex = ((i % TRACKS.length) + TRACKS.length) % TRACKS.length;
  const src = TRACKS[trackIndex];
  if (current) {
    current.onended = null;
    try {
      current.pause();
    } catch {
      /* ignore */
    }
  }
  const a = new Audio(src);
  a.preload = "auto";
  a.volume = 0;
  a.loop = false;
  a.onended = () => playIndex(trackIndex + 1);
  current = a;
  void a.play().then(() => fadeTo(a, MUSIC_VOLUME, FADE_MS)).catch(() => {
    // Autoplay blocked until a gesture; retry on next pointerdown
    const retry = () => {
      window.removeEventListener("pointerdown", retry);
      if (!started || fadedOut) return;
      void a.play().then(() => fadeTo(a, MUSIC_VOLUME, FADE_MS)).catch(() => {});
    };
    window.addEventListener("pointerdown", retry, { once: true });
  });
}

/** Start the Iron Mesa playlist when the battle screen mounts. */
export function startBattleMusic(): void {
  unlockSfx();
  if (started && current && !current.paused) return;
  started = true;
  fadedOut = false;
  playIndex(0);
}

/** Fade out and stop when leaving battle. */
export function stopBattleMusic(): void {
  started = false;
  fadedOut = true;
  const a = current;
  current = null;
  if (!a) return;
  a.onended = null;
  fadeTo(a, 0, FADE_MS, () => {
    try {
      a.pause();
      a.currentTime = 0;
    } catch {
      /* ignore */
    }
  });
}
