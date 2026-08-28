import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  screenClassName?: string;
};

/** Battle-hardened commander tablet bezel shared by map, army builder, and battlefield. */
export function TabletFrame({ children, className = "", screenClassName = "" }: Props) {
  return (
    <div className={["tablet-frame", className].filter(Boolean).join(" ")}>
      <div className="tablet-bezel">
        <span className="tablet-rivet tl" aria-hidden="true" />
        <span className="tablet-rivet tr" aria-hidden="true" />
        <span className="tablet-rivet bl" aria-hidden="true" />
        <span className="tablet-rivet br" aria-hidden="true" />
        <span className="tablet-bumper left" aria-hidden="true" />
        <span className="tablet-bumper right" aria-hidden="true" />
        <span className="tablet-slot top" aria-hidden="true" />
        <span className="tablet-slot bottom" aria-hidden="true" />
        <div className={["tablet-screen", screenClassName].filter(Boolean).join(" ")}>{children}</div>
      </div>
    </div>
  );
}
