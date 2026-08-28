/** Lightweight SFX player for Drone Commander UI + combat cues. */

export type SfxId =
  | "ui_click"
  | "ui_primary"
  | "ui_select"
  | "hex_select"
  | "move_confirm"
  | "attack_fire"
  | "fire_rifle_burst"
  | "fire_commander_shotgun"
  | "fire_commander_sniper"
  | "attack_impact"
  | "hit_gunfire"
  | "explosion_small"
  | "explosion_large"
  | "ram_ability"
  | "end_activation"
  | "directive"
  | "hold"
  | "deploy"
  | "drone_select_friendly"
  | "drone_select_opposition"
  | "drone_select_support"
  | "hex_scan_laser"
  | "hex_scan_engine";

const SRC: Record<SfxId, string> = {
  ui_click: "/assets/sfx/ui_click.mp3",
  ui_primary: "/assets/sfx/ui_primary.mp3",
  ui_select: "/assets/sfx/ui_select.mp3",
  hex_select: "/assets/sfx/hex_select.mp3",
  move_confirm: "/assets/sfx/move_confirm.mp3",
  attack_fire: "/assets/sfx/attack_fire.mp3",
  fire_rifle_burst: "/assets/sfx/fire_rifle_burst.mp3",
  fire_commander_shotgun: "/assets/sfx/fire_commander_shotgun.mp3",
  fire_commander_sniper: "/assets/sfx/fire_commander_sniper.mp3",
  attack_impact: "/assets/sfx/attack_impact.mp3",
  hit_gunfire: "/assets/sfx/hit_gunfire.mp3",
  explosion_small: "/assets/sfx/explosion_small.mp3",
  explosion_large: "/assets/sfx/explosion_large.mp3",
  ram_ability: "/assets/sfx/ram_ability.mp3",
  end_activation: "/assets/sfx/end_activation.mp3",
  directive: "/assets/sfx/directive.mp3",
  hold: "/assets/sfx/hold.mp3",
  deploy: "/assets/sfx/deploy.mp3",
  drone_select_friendly: "/assets/sfx/drone_select_friendly.mp3",
  drone_select_opposition: "/assets/sfx/drone_select_opposition.mp3",
  drone_select_support: "/assets/sfx/drone_select_support.mp3",
  hex_scan_laser: "/assets/sfx/hex_scan_laser.mp3",
  hex_scan_engine: "/assets/sfx/hex_scan_engine.mp3",
};

const VOLUME: Partial<Record<SfxId, number>> = {
  ui_click: 0.45,
  ui_primary: 0.55,
  ui_select: 0.5,
  hex_select: 0.35,
  move_confirm: 0.55,
  attack_fire: 0.7,
  fire_rifle_burst: 0.78,
  fire_commander_shotgun: 0.95,
  fire_commander_sniper: 0.62,
  attack_impact: 0.65,
  hit_gunfire: 0.8,
  explosion_small: 0.85,
  explosion_large: 1.0,
  ram_ability: 0.65,
  end_activation: 0.6,
  directive: 0.55,
  hold: 0.5,
  deploy: 0.7,
  drone_select_friendly: 0.55,
  drone_select_opposition: 0.55,
  drone_select_support: 0.55,
  hex_scan_laser: 0.28,
  hex_scan_engine: 0.55,
};

const VO_LINES = {
  commander_male: [
    "/assets/sfx/select_commander_01.mp3",
    "/assets/sfx/select_commander_02.mp3",
    "/assets/sfx/select_commander_03.mp3",
  ],
  commander_female: [
    "/assets/sfx/select_commander_female_01.mp3",
    "/assets/sfx/select_commander_female_02.mp3",
    "/assets/sfx/select_commander_female_03.mp3",
  ],
  infantry_friendly: [
    "/assets/sfx/select_infantry_friendly_01.mp3",
    "/assets/sfx/select_infantry_friendly_02.mp3",
    "/assets/sfx/select_infantry_friendly_03.mp3",
  ],
  infantry_opposition: [
    "/assets/sfx/select_infantry_opposition_01.mp3",
    "/assets/sfx/select_infantry_opposition_02.mp3",
    "/assets/sfx/select_infantry_opposition_03.mp3",
  ],
} as const;

const ARMY_ORDER_VO_MALE: Record<string, string> = {
  push_center: "/assets/sfx/order_push_center.mp3",
  hold_defend_line: "/assets/sfx/order_hold_defend_line.mp3",
  focus_fire: "/assets/sfx/order_focus_fire.mp3",
  screen_commander: "/assets/sfx/order_screen_commander.mp3",
  advance_and_engage: "/assets/sfx/order_advance_and_engage.mp3",
};

const ARMY_ORDER_VO_FEMALE: Record<string, string> = {
  push_center: "/assets/sfx/order_push_center_female.mp3",
  hold_defend_line: "/assets/sfx/order_hold_defend_line_female.mp3",
  focus_fire: "/assets/sfx/order_focus_fire_female.mp3",
  screen_commander: "/assets/sfx/order_screen_commander_female.mp3",
  advance_and_engage: "/assets/sfx/order_advance_and_engage_female.mp3",
};

let unlocked = false;
let enabled = true;
const cache = new Map<string, HTMLAudioElement>();
let lastUiClickAt = 0;
const voIndex: Record<string, number> = {};

function getAudioBySrc(src: string): HTMLAudioElement {
  let a = cache.get(src);
  if (!a) {
    a = new Audio(src);
    a.preload = "auto";
    cache.set(src, a);
  }
  return a;
}

function getAudio(id: SfxId): HTMLAudioElement {
  return getAudioBySrc(SRC[id]);
}

function playSrc(src: string, volume = 0.7): void {
  if (!enabled) return;
  unlockSfx();
  try {
    const base = getAudioBySrc(src);
    const a = base.cloneNode(true) as HTMLAudioElement;
    a.volume = volume;
    void a.play().catch(() => {});
  } catch {
    /* ignore */
  }
}

function nextLine(key: keyof typeof VO_LINES): string {
  const lines = VO_LINES[key];
  const i = voIndex[key] ?? 0;
  voIndex[key] = (i + 1) % lines.length;
  return lines[i];
}

function commanderVoKey(avatar?: string): "commander_female" | "commander_male" {
  return avatar === "female" ? "commander_female" : "commander_male";
}

/** Call once on first user gesture so browsers allow playback. */
export function unlockSfx(): void {
  if (unlocked) return;
  unlocked = true;
  const a = getAudio("ui_click");
  a.volume = 0;
  void a
    .play()
    .then(() => {
      a.pause();
      a.currentTime = 0;
      a.volume = VOLUME.ui_click ?? 0.45;
    })
    .catch(() => {});
}

export function setSfxEnabled(on: boolean): void {
  enabled = on;
}

/** Pick gunfire SFX from weapon + unit context (infantry burst, commander shotgun/sniper). */
export function fireSfxForAttack(opts: {
  weaponId?: string;
  category?: string;
  commanderAvatar?: string;
  actorSide?: string;
}): SfxId {
  const weaponId = opts.weaponId || "";
  const category = opts.category || "";
  // Combat Engineers (both sides) carry shotguns — always the boom, never the sniper swap.
  if (weaponId === "shotgun") {
    return "fire_commander_shotgun";
  }
  if (category === "commander" || weaponId === "commander_carbine" || weaponId === "commander_sniper") {
    let avatar = opts.commanderAvatar === "female" ? "female" : "male";
    if (opts.actorSide === "opposition") {
      avatar = avatar === "female" ? "male" : "female";
    }
    return avatar === "female" ? "fire_commander_sniper" : "fire_commander_shotgun";
  }
  if (weaponId === "rifle" || weaponId === "heavy_rifle" || category === "soldier_squad") {
    return "fire_rifle_burst";
  }
  return "attack_fire";
}

export function playSfx(id: SfxId): void {
  if (!enabled) return;
  unlockSfx();
  try {
    const base = getAudio(id);
    const a = base.cloneNode(true) as HTMLAudioElement;
    a.volume = VOLUME[id] ?? 0.5;
    void a.play().catch(() => {});
  } catch {
    /* ignore missing assets / autoplay */
  }
}

/** Play a longer bed (engine pass, etc.) and return the element so callers can stop/fade it. */
export function playSfxBed(id: SfxId, volume?: number): HTMLAudioElement | null {
  if (!enabled) return null;
  unlockSfx();
  try {
    const base = getAudio(id);
    const a = base.cloneNode(true) as HTMLAudioElement;
    a.volume = volume ?? VOLUME[id] ?? 0.5;
    void a.play().catch(() => {});
    return a;
  } catch {
    return null;
  }
}

export function stopAudio(a: HTMLAudioElement | null | undefined, fadeMs = 180): void {
  if (!a) return;
  try {
    if (fadeMs <= 0) {
      a.pause();
      a.currentTime = 0;
      return;
    }
    const start = a.volume;
    const t0 = performance.now();
    const tick = () => {
      const t = Math.min(1, (performance.now() - t0) / fadeMs);
      a.volume = Math.max(0, start * (1 - t));
      if (t < 1) requestAnimationFrame(tick);
      else {
        a.pause();
        a.currentTime = 0;
      }
    };
    requestAnimationFrame(tick);
  } catch {
    /* ignore */
  }
}

/** StarCraft-style select acknowledgement for a unit snapshot. */
export function playUnitSelectAck(
  unit: {
    category?: string;
    side?: string;
    roles?: string[];
    definition_id?: string;
  } | null | undefined,
  commanderAvatar?: string,
): void {
  if (!unit) return;
  const category = unit.category || "";
  const side = unit.side || "friendly";
  const roles = unit.roles || [];

  if (category === "commander") {
    playSrc(nextLine(commanderVoKey(commanderAvatar)), 0.8);
    return;
  }
  if (category === "soldier_squad") {
    playSrc(nextLine(side === "opposition" ? "infantry_opposition" : "infantry_friendly"), 0.75);
    return;
  }
  if (category === "drone") {
    if (side === "opposition") {
      playSfx("drone_select_opposition");
      return;
    }
    if (
      roles.includes("support") ||
      String(unit.definition_id || "").includes("support") ||
      String(unit.definition_id || "").includes("recovery")
    ) {
      playSfx("drone_select_support");
      return;
    }
    playSfx("drone_select_friendly");
  }
}

/** Play commander VO when issuing a premade army order. */
export function playArmyOrderVo(orderId: string, commanderAvatar?: string): void {
  const table = commanderAvatar === "female" ? ARMY_ORDER_VO_FEMALE : ARMY_ORDER_VO_MALE;
  const src = table[orderId];
  if (!src) {
    playSfx("directive");
    return;
  }
  playSrc(src, 0.85);
}

function classifyButton(btn: HTMLButtonElement): SfxId {
  if (btn.disabled) return "ui_click";
  if (btn.dataset.sfx === "order") return "directive";
  const text = `${btn.className} ${btn.textContent || ""}`.toLowerCase();
  if (/deploy/.test(text)) return "deploy";
  if (/end activation/.test(text)) return "end_activation";
  if (/queue directive|issue directive|issue custom order|custom…/.test(text)) return "directive";
  if (/\bhold\b/.test(text) && !/hold \/|hold the|defend/.test(text)) return "hold";
  if (btn.classList.contains("mode-btn") || /move \(|attack \(|ram \(/.test(text)) {
    return "ui_select";
  }
  if (btn.classList.contains("primary") || /confirm|rematch|dismiss/.test(text)) {
    return "ui_primary";
  }
  if (/fire |attack |self-destruct/.test(text)) return "attack_fire";
  if (/use |ram |satellite|targeting|defense matrix|airstrike/.test(text)) return "ram_ability";
  return "ui_click";
}

/** Global capture: every real button click gets a cue. */
export function installGlobalButtonSfx(): () => void {
  const onPointerDown = () => unlockSfx();
  const onClick = (e: MouseEvent) => {
    const t = e.target as HTMLElement | null;
    if (!t) return;
    const btn = t.closest("button");
    if (!btn) return;
    const now = performance.now();
    if (now - lastUiClickAt < 40) return;
    lastUiClickAt = now;
    if (btn.dataset.sfxPlayed === "1") {
      delete btn.dataset.sfxPlayed;
      return;
    }
    // Initiative cards play unit select VO instead of generic click
    if (btn.classList.contains("init-card")) return;
    // Army order chips play commander VO from the click handler
    if (btn.dataset.sfx === "order") return;
    // Attack/RAM option buttons play combat cues from playStepFeedback instead
    if (btn.dataset.sfx === "combat") return;
    playSfx(classifyButton(btn));
  };
  window.addEventListener("pointerdown", onPointerDown, { passive: true });
  window.addEventListener("click", onClick, true);
  return () => {
    window.removeEventListener("pointerdown", onPointerDown);
    window.removeEventListener("click", onClick, true);
  };
}

/** Mark that a button already played a specific cue (prevents double UI click). */
export function markSfxHandled(el: EventTarget | null): void {
  if (el instanceof HTMLElement) {
    const btn = el.closest("button");
    if (btn) btn.dataset.sfxPlayed = "1";
  }
}
