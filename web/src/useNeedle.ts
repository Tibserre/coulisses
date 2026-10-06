import { useEffect, useRef } from "react";
import { step, type Needle } from "./smoothLevel.ts";

/** Draws the smoothed level at each screen frame (`draw` writes to the DOM itself: no
 *  React render per frame). With reduced motion, the level is shown as it comes. */
export function useNeedle(level: number, peak: number, draw: (needle: Needle) => void): void {
  const target = useRef({ level, peak });
  target.current = { level, peak };
  const drawRef = useRef(draw);
  drawRef.current = draw;

  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let needle: Needle = { level: 0, peak: 0, held: 0 };
    let last = performance.now();
    let id = 0;
    const frame = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000); // a hidden tab resumes without a jump
      last = now;
      const { level: to, peak: top } = target.current;
      needle = reduce ? { level: to, peak: top, held: 0 } : step(needle, to, top, dt);
      drawRef.current(needle);
      id = requestAnimationFrame(frame);
    };
    id = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(id);
  }, []);
}
