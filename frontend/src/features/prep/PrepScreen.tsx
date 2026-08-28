import { useMemo, useState } from "react";
import type { MatchSetup } from "../setup/MatchSetupScreen";
import { unitReadyUrl } from "../../pixi/unitSprites";
import { TabletFrame } from "../../components/TabletFrame";
import { useIsPhone } from "../../hooks/useIsPhone";

/** Default loadout for both male and female commanders. */
const DEFAULT_RAM_ABILITIES = ["defense_matrix", "call_for_action", "targeting_assistance"];

type Props = {
  boot: any;
  initialPrep: any;
  matchSetup: MatchSetup;
  onDeploy: (prep: any, seed?: number) => Promise<void>;
  onBack: () => void;
  onError: (msg: string) => void;
};

export function PrepScreen({ boot, initialPrep, matchSetup, onDeploy, onBack, onError }: Props) {
  const isPhone = useIsPhone();
  const pointCap = matchSetup.pointCap;
  const [avatar, setAvatar] = useState(initialPrep?.avatar || "male");
  const [abilities, setAbilities] = useState<string[]>(() => {
    const fromPrep = initialPrep?.ram_abilities;
    if (Array.isArray(fromPrep) && fromPrep.length === 3) return fromPrep;
    return [...DEFAULT_RAM_ABILITIES];
  });
  const [army, setArmy] = useState<Record<string, number>>(() => {
    const map: Record<string, number> = {};
    for (const e of initialPrep?.army || []) map[e.definition_id] = e.count;
    return map;
  });
  const [busy, setBusy] = useState(false);

  const commander = boot.avatars.find((a: any) => a.id === avatar);
  const allowed = new Set(commander?.allowed_abilities || []);

  const abilityById = useMemo(() => {
    const map = new Map<string, any>();
    for (const a of boot.abilities || []) map.set(a.id, a);
    return map;
  }, [boot.abilities]);

  const points = useMemo(() => {
    let total = 0;
    for (const [id, count] of Object.entries(army)) {
      const u = boot.units.find((x: any) => x.id === id);
      if (u) total += u.point_cost * count;
    }
    return total;
  }, [army, boot.units]);

  const unitCount = Object.values(army).reduce((a, b) => a + b, 0);
  const validation: string[] = [];
  if (abilities.length !== 3) validation.push("Select exactly 3 RAM abilities");
  if (points > pointCap) validation.push(`Points ${points} exceed cap ${pointCap}`);
  if (unitCount < 1) validation.push("Add at least one unit");
  if (unitCount > 10) validation.push("Max 10 units");

  function toggleAbility(id: string) {
    setAbilities((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 3) return prev;
      return [...prev, id];
    });
  }

  function setCount(id: string, count: number) {
    setArmy((prev) => {
      const next = { ...prev };
      if (count <= 0) delete next[id];
      else next[id] = count;
      return next;
    });
  }

  const scenario = boot?.scenarios?.find((s: any) => s.id === matchSetup.scenarioId);
  const scenarioBlurb = scenario?.description || "First to 5 victory points wins.";

  async function deploy() {
    if (validation.length) return;
    setBusy(true);
    try {
      await onDeploy({
        avatar,
        ram_abilities: abilities,
        mode: "freestyle_vs",
        mission_id: "freestyle_vs_15",
        map_id: matchSetup.mapId,
        point_cap: pointCap,
        scenario_id: matchSetup.scenarioId,
        army: Object.entries(army).map(([definition_id, count]) => ({ definition_id, count })),
      });
    } catch (e: any) {
      onError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="menu-tablet-page prep-page">
      <TabletFrame className="menu-tablet" screenClassName="menu-tablet-screen">
        <div className="prep-inner stack">
          <div className="row prep-top">
            <button onClick={onBack} data-sfx="ui_click">
              {isPhone ? "Back" : "Back to Map"}
            </button>
            <div className="muted prep-meta">
              {isPhone
                ? `${matchSetup.mapName} · ${pointCap} pts`
                : `${matchSetup.mapName} · ${pointCap}-point Freestyle · ${matchSetup.scenarioName}`}
            </div>
          </div>
          <header className="prep-header stack">
            <h1>Army Builder</h1>
            {!isPhone && <p className="muted">{scenarioBlurb}</p>}
          </header>

          <section className="panel stack prep-section">
            <h3>1. Commander</h3>
            {!isPhone && <p className="muted">Avatar choice sets commander base stats and weapons.</p>}
            <div className="row prep-avatar-row">
              {boot.avatars.map((a: any) => (
                <button
                  key={a.id}
                  className={avatar === a.id ? "primary" : ""}
                  onClick={() => {
                    setAvatar(a.id);
                    setAbilities([...DEFAULT_RAM_ABILITIES]);
                  }}
                >
                  {isPhone ? (a.id === "male" ? "Diego" : "Sanna") : a.label}
                </button>
              ))}
            </div>
            {commander && (
              <div className="unit-card commander-card">
                <div className="unit-card-main">
                  <img
                    className="unit-ready-thumb"
                    src={unitReadyUrl({ definition_id: "friendly_commander", category: "commander" }, avatar)}
                    alt=""
                  />
                  <div className="unit-card-copy">
                    <strong>{commander.label}</strong>
                    <div className="muted unit-stats">
                      Spd {commander.speed} · Atk +{commander.attack} · Def {commander.defense} · Arm {commander.armor} ·
                      HP {commander.hp} · RAM {commander.ram_capacity} · Signal {commander.ram_capacity * 2}
                    </div>
                    {!isPhone && commander.passive && <div className="muted">{commander.passive}</div>}
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className="panel stack prep-section">
            <h3>2. RAM Abilities ({abilities.length}/3)</h3>
            <div className="row prep-ability-row">
              {boot.abilities
                .filter((a: any) => allowed.has(a.id) && a.ram_cost > 0)
                .map((a: any) => (
                  <button
                    key={a.id}
                    className={abilities.includes(a.id) ? "primary" : ""}
                    title={a.description || a.display_name}
                    onClick={() => toggleAbility(a.id)}
                  >
                    {a.display_name} ({a.ram_cost})
                  </button>
                ))}
            </div>
          </section>

          <section className="panel stack prep-section prep-army-section">
            <h3>
              3. Army · {points}/{pointCap} pts · {unitCount}/10
            </h3>
            <div className="prep-unit-list">
              {boot.units.map((u: any) => {
                const readySrc = unitReadyUrl({
                  definition_id: u.id,
                  asset_set_id: u.asset_set_id,
                  category: u.category,
                  side: "friendly",
                });
                return (
                  <div className="unit-card" key={u.id}>
                    <div className="unit-card-main">
                      <img className="unit-ready-thumb" src={readySrc} alt="" />
                      <div className="unit-card-copy">
                        <strong>
                          {u.display_name}
                          <span className="muted unit-cost"> · {u.point_cost} pts</span>
                        </strong>
                        <div className="muted unit-stats">
                          Spd {u.speed} · Def {u.defense} · Arm {u.armor} · HP {u.hp_per_model}
                          {u.model_count > 1 ? ` ×${u.model_count}` : ""}
                        </div>
                        {!isPhone && u.abilities?.length > 0 && (
                          <div className="muted">
                            {u.abilities
                              .map((id: string) => abilityById.get(id)?.display_name || id)
                              .join(" · ")}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="row unit-qty">
                      <button onClick={() => setCount(u.id, (army[u.id] || 0) - 1)} aria-label={`Remove ${u.display_name}`}>
                        -
                      </button>
                      <span>{army[u.id] || 0}</span>
                      <button onClick={() => setCount(u.id, (army[u.id] || 0) + 1)} aria-label={`Add ${u.display_name}`}>
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className={`panel stack prep-section prep-deploy ${isPhone ? "prep-deploy-sticky" : ""}`}>
            {!isPhone && <h3>4. Review & Deploy</h3>}
            {validation.map((v) => (
              <div className="err" key={v}>
                {v}
              </div>
            ))}
            <div className="row prep-deploy-row">
              {isPhone && (
                <div className="prep-deploy-summary">
                  <strong>
                    {points}/{pointCap}
                  </strong>
                  <span className="muted">{unitCount}/10 units</span>
                </div>
              )}
              <button className="primary prep-deploy-btn" disabled={!!validation.length || busy} onClick={deploy}>
                {busy ? "Deploying…" : "Deploy"}
              </button>
            </div>
          </section>
        </div>
      </TabletFrame>
    </div>
  );
}
