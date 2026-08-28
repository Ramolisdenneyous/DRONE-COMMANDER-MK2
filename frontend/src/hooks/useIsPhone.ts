import { useEffect, useState } from "react";

/** Pixel 7 CSS width is 412; treat ≤480 portrait-ish viewports as phone. */
export const PHONE_MAX_WIDTH = 480;

export function useIsPhone(maxWidth = PHONE_MAX_WIDTH): boolean {
  const [isPhone, setIsPhone] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(`(max-width: ${maxWidth}px)`).matches;
  });

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const onChange = () => setIsPhone(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [maxWidth]);

  return isPhone;
}
