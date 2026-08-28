import { useIsPhone } from "../../hooks/useIsPhone";

type Props = {
  ready: boolean;
  onEnter: () => void;
};

export function SplashScreen({ ready, onEnter }: Props) {
  const isPhone = useIsPhone();
  const artSrc = isPhone ? "/assets/landing/splash-phone.png" : "/assets/landing/splash.png";

  return (
    <div className={`splash ${isPhone ? "splash-phone" : "splash-desktop"}`}>
      <div className="splash-stage">
        <img
          className="splash-art"
          src={artSrc}
          alt="Drone Commander — both commanders on the battlefield"
        />
        <div className="splash-scrim" />
      </div>
      <div className="splash-cta">
        <button className="splash-enter primary" disabled={!ready} onClick={onEnter} data-sfx="ui_primary">
          {ready ? "Enter Theater" : "Loading…"}
        </button>
        <p className="splash-sub muted">Select battlefield · Build your force · Command the swarm</p>
      </div>
    </div>
  );
}
