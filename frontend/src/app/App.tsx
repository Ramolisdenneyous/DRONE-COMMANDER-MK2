import { useEffect, useState } from "react";
import { api } from "../api/client";
import { installGlobalButtonSfx } from "../audio/sfx";
import { SplashScreen } from "../features/splash/SplashScreen";
import { MatchSetupScreen, type MatchSetup } from "../features/setup/MatchSetupScreen";
import { PrepScreen } from "../features/prep/PrepScreen";
import { BattleScreen } from "../features/battle/BattleScreen";
import { DebriefScreen } from "../features/debrief/DebriefScreen";
import { useIsPhone } from "../hooks/useIsPhone";

type Screen = "splash" | "setup" | "prep" | "battle" | "debrief";

export function App() {
  const isPhone = useIsPhone();
  const [boot, setBoot] = useState<any>(null);
  const [session, setSession] = useState<any>(null);
  const [battle, setBattle] = useState<any>(null);
  const [matchSetup, setMatchSetup] = useState<MatchSetup | null>(null);
  const [screen, setScreen] = useState<Screen>("splash");
  const [error, setError] = useState<string | null>(null);
  const [showTutorial, setShowTutorial] = useState(() => !localStorage.getItem("dc_tutorial_dismissed"));

  useEffect(() => {
    return installGlobalButtonSfx();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.device = isPhone ? "phone" : "desktop";
    document.body.dataset.device = isPhone ? "phone" : "desktop";
  }, [isPhone]);

  useEffect(() => {
    (async () => {
      try {
        const [b, s] = await Promise.all([api.boot(), api.createSession()]);
        setBoot(b);
        setSession(s);
      } catch (e: any) {
        setError(e.message || String(e));
      }
    })();
  }, []);

  async function onDeploy(prep: any, seed?: number) {
    setError(null);
    const updated = await api.updatePrep(session.session_id, prep);
    setSession(updated);
    const result = await api.deploy(session.session_id, seed);
    setSession(result.session);
    setBattle(result.battle);
    setScreen(result.battle.status === "ACTIVE" ? "battle" : "debrief");
  }

  function onBattleUpdate(next: any) {
    setBattle(next);
    if (next.status && next.status !== "ACTIVE") {
      setScreen("debrief");
    }
  }

  async function onRematch() {
    const s = await api.createSession();
    setSession(s);
    setBattle(null);
    setScreen("setup");
  }

  const ready = !!(boot && session);

  return (
    <div className={`app-shell ${isPhone ? "is-phone" : "is-desktop"}`} data-device={isPhone ? "phone" : "desktop"}>
      {screen !== "splash" && !(isPhone && screen === "battle") && (
        <header className="topbar">
          <div className="brand">DRONE COMMANDER MK2</div>
          <div className="muted topbar-meta">
            {isPhone
              ? matchSetup
                ? `${matchSetup.mapName} · ${matchSetup.pointCap} pts`
                : boot
                  ? `v ${boot.content_version}`
                  : "booting…"
              : `${boot ? `content ${boot.content_version}` : "booting…"}${
                  matchSetup ? ` · ${matchSetup.mapName} · ${matchSetup.pointCap} pts · ${matchSetup.scenarioName}` : ""
                }${session ? ` · session ${session.session_id.slice(0, 8)}` : ""}`}
          </div>
        </header>
      )}

      {showTutorial && screen === "prep" && !isPhone && (
        <div className="panel" style={{ margin: "1rem" }}>
          <h2>Command Brief</h2>
          <p>
            You are the vulnerable battlefield commander. Move, fight, and spend RAM on your activation. Issue army orders
            anytime over the radio — squads and drones follow the latest standing order on their activations, even mid-round.
          </p>
          <button
            className="primary"
            onClick={() => {
              localStorage.setItem("dc_tutorial_dismissed", "1");
              setShowTutorial(false);
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {error && screen !== "splash" && (
        <div className="err" style={{ padding: "0.75rem 1rem" }}>
          {error}
        </div>
      )}

      {screen === "splash" ? (
        <SplashScreen
          ready={ready}
          onEnter={() => {
            if (!ready) return;
            setScreen("setup");
          }}
        />
      ) : !boot || !session ? (
        <div className="boot-wait">
          <img src="/assets/landing/logo.png" alt="" />
          <p>{error || "Loading catalog…"}</p>
        </div>
      ) : screen === "setup" ? (
        <MatchSetupScreen
          boot={boot}
          initial={matchSetup}
          onBack={() => setScreen("splash")}
          onContinue={(setup) => {
            setMatchSetup(setup);
            setScreen("prep");
          }}
        />
      ) : screen === "prep" && matchSetup ? (
        <PrepScreen
          boot={boot}
          initialPrep={session.prep}
          matchSetup={matchSetup}
          onBack={() => setScreen("setup")}
          onDeploy={onDeploy}
          onError={setError}
        />
      ) : screen === "battle" && battle ? (
        <BattleScreen battle={battle} boot={boot} onUpdate={onBattleUpdate} onError={setError} />
      ) : battle ? (
        <DebriefScreen
          battle={battle}
          sessionId={session.session_id}
          onRematch={onRematch}
          onReview={() => setScreen("battle")}
        />
      ) : null}
    </div>
  );
}
