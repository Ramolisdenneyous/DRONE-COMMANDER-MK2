import { useMemo, useState } from "react";
import { TabletFrame } from "../../components/TabletFrame";
import { useIsPhone } from "../../hooks/useIsPhone";

export type MatchSetup = {
  mapId: string;
  mapName: string;
  pointCap: number;
  scenarioId: string;
  scenarioName: string;
};

type MapOption = {
  id: string;
  display_name: string;
  select_asset: string;
  ground_asset?: string;
};

type ScenarioOption = {
  id: string;
  display_name: string;
  description: string;
  default?: boolean;
};

type Props = {
  boot: any;
  initial?: MatchSetup | null;
  onContinue: (setup: MatchSetup) => void;
  onBack: () => void;
};

const FALLBACK_MAPS: MapOption[] = [
  {
    id: "vs_middle_east_50",
    display_name: "Middle East",
    select_asset: "/assets/maps/middle-east/select.png",
  },
  {
    id: "freestyle_northern_tundra_50",
    display_name: "Northern Tundra",
    select_asset: "/assets/maps/northern-tundra/select.png",
  },
  {
    id: "freestyle_open_fields_50",
    display_name: "Open Fields",
    select_asset: "/assets/maps/open-fields/select.png",
  },
  {
    id: "freestyle_urban_combat_50",
    display_name: "Urban Combat",
    select_asset: "/assets/maps/urban-combat/select.png",
  },
];

const FALLBACK_SCENARIOS: ScenarioOption[] = [
  {
    id: "point_control",
    display_name: "Point Control",
    description: "Hold the central zone uncontested at round end for 1 VP. First to 5 VP wins.",
    default: true,
  },
  {
    id: "four_corners",
    display_name: "Four Corners",
    description: "Four zones between center and corners. Score 1 VP per zone held at round end.",
  },
  {
    id: "hold_the_line",
    display_name: "Hold the Line",
    description: "Three zones across the map midline. Score 1 VP per zone held at round end.",
  },
  {
    id: "capture_the_flags",
    display_name: "Capture the Flags",
    description: "Grab flags with a unit action. Flags move with the carrier until killed. 1 VP per flag held at round end.",
  },
];

type PhoneStep = "map" | "rules";

export function MatchSetupScreen({ boot, initial, onContinue, onBack }: Props) {
  const isPhone = useIsPhone();
  const maps: MapOption[] = useMemo(() => {
    const fromBoot = Array.isArray(boot?.maps) ? boot.maps : [];
    return fromBoot.length ? fromBoot : FALLBACK_MAPS;
  }, [boot]);

  const scenarios: ScenarioOption[] = useMemo(() => {
    const fromBoot = Array.isArray(boot?.scenarios) ? boot.scenarios : [];
    return fromBoot.length ? fromBoot : FALLBACK_SCENARIOS;
  }, [boot]);

  const pointCaps: number[] = useMemo(() => {
    const caps = Array.isArray(boot?.point_caps) ? boot.point_caps : [15, 25, 40, 55, 75, 100];
    return caps;
  }, [boot]);

  const defaultScenario = scenarios.find((s) => s.default) || scenarios[0];

  const [mapId, setMapId] = useState(initial?.mapId || maps[0]?.id || "vs_middle_east_50");
  const [pointCap, setPointCap] = useState(initial?.pointCap || pointCaps[0] || 15);
  const [scenarioId, setScenarioId] = useState(initial?.scenarioId || defaultScenario?.id || "point_control");
  const [phoneStep, setPhoneStep] = useState<PhoneStep>("map");

  const selected = maps.find((m) => m.id === mapId) || maps[0];
  const selectedScenario = scenarios.find((s) => s.id === scenarioId) || defaultScenario;

  function submit() {
    onContinue({
      mapId,
      mapName: selected?.display_name || mapId,
      pointCap,
      scenarioId,
      scenarioName: selectedScenario?.display_name || scenarioId,
    });
  }

  const showMap = !isPhone || phoneStep === "map";
  const showRules = !isPhone || phoneStep === "rules";

  return (
    <div className="menu-tablet-page">
      <TabletFrame className="menu-tablet" screenClassName="menu-tablet-screen">
        <div className="match-setup-inner stack">
          <div className="row match-setup-top">
            <button
              onClick={() => {
                if (isPhone && phoneStep === "rules") {
                  setPhoneStep("map");
                  return;
                }
                onBack();
              }}
              data-sfx="ui_click"
            >
              {isPhone && phoneStep === "rules" ? "Back to Maps" : "Back"}
            </button>
            <img className="match-logo" src="/assets/landing/logo.png" alt="Drone Commander" />
            {isPhone ? (
              <span className="muted match-step-indicator">{phoneStep === "map" ? "1 / 2" : "2 / 2"}</span>
            ) : (
              <span className="match-top-spacer" />
            )}
          </div>

          {showMap && (
            <>
              <header className="stack match-section-head">
                <h1>Choose Battlefield</h1>
                {!isPhone && <p className="muted">Click a theater to select the terrain tileset for this match.</p>}
              </header>

              <div className="map-grid" role="listbox" aria-label="Battlefield maps">
                {maps.map((m) => {
                  const active = m.id === mapId;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      role="option"
                      aria-selected={active}
                      className={`map-card ${active ? "selected" : ""}`}
                      onClick={() => setMapId(m.id)}
                      data-sfx="ui_select"
                    >
                      <img src={m.select_asset} alt="" />
                      <span className="map-card-label">{m.display_name}</span>
                    </button>
                  );
                })}
              </div>

              {isPhone && (
                <div className="row match-nav-actions">
                  <button
                    className="primary"
                    data-sfx="ui_primary"
                    onClick={() => setPhoneStep("rules")}
                  >
                    Next: Points & Scenario
                  </button>
                </div>
              )}
            </>
          )}

          {showRules && (
            <>
              {isPhone && (
                <header className="stack match-section-head">
                  <h1>Match Rules</h1>
                  <p className="muted">{selected?.display_name}</p>
                </header>
              )}

              <section className="panel stack">
                <h3>Point Cap</h3>
                {!isPhone && (
                  <p className="muted">Higher caps unlock larger armies. Start with 15 if you are learning the loop.</p>
                )}
                <div className="row point-caps">
                  {pointCaps.map((cap) => (
                    <button
                      key={cap}
                      type="button"
                      className={pointCap === cap ? "primary" : ""}
                      onClick={() => setPointCap(cap)}
                      data-sfx="ui_click"
                    >
                      {cap}
                    </button>
                  ))}
                </div>
              </section>

              <section className="panel stack">
                <h3>Scenario</h3>
                {!isPhone && (
                  <p className="muted">
                    First player to 5 victory points wins. Zones are controlled within 5 hexes of each objective point.
                  </p>
                )}
                <div className="scenario-grid" role="listbox" aria-label="Freestyle scenarios">
                  {scenarios.map((s) => {
                    const active = s.id === scenarioId;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        role="option"
                        aria-selected={active}
                        className={`scenario-card ${active ? "selected" : ""}`}
                        onClick={() => setScenarioId(s.id)}
                        data-sfx="ui_select"
                      >
                        <strong>{s.display_name}</strong>
                        <span className="muted">{s.description}</span>
                      </button>
                    );
                  })}
                </div>
              </section>

              <div className="row match-nav-actions">
                <button className="primary" data-sfx="ui_primary" onClick={submit}>
                  Continue to Army Builder
                </button>
              </div>
            </>
          )}
        </div>
      </TabletFrame>
    </div>
  );
}
