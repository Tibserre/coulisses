import { useEffect, useRef } from "react";
import { step, type Needle } from "./smoothLevel.ts";

/** Draws the smoothed level at each screen frame (`draw` writes to the DOM itself: no
 *  React render per frame), and only while it moves: settled, the loop stops until a new
 *  value comes (no work for nothing during a two-hour session). With reduced motion,
 *  followed live, the level is shown as it comes. */
export function useNeedle(level: number, peak: number, draw: (needle: Needle) => void): void {
  const target = useRef({ level, peak });
  target.current = { level, peak };
  const drawRef = useRef(draw);
  drawRef.current = draw;
  const needle = useRef<Needle>({ level: 0, peak: 0, held: 0 });
  const frameId = useRef<number | null>(null);
  const last = useRef(0);
  const reduce = useRef(false);

  const frame = useRef((now: number) => {
    const dt = Math.min(0.1, (now - last.current) / 1000); // a hidden tab resumes without a jump
    last.current = now;
    const { level: to, peak: top } = target.current;
    const next = reduce.current ? { level: to, peak: top, held: 0 } : step(needle.current, to, top, dt);
    needle.current = next;
    drawRef.current(next);
    const settled = Math.abs(next.level - to) < 0.05 && next.peak <= Math.max(top, next.level) + 0.05;
    frameId.current = settled ? null : requestAnimationFrame(frame.current);
  });

  // A new value (or the first one): the loop runs again until the needle settles.
  useEffect(() => {
    if (frameId.current === null) {
      last.current = performance.now();
      frameId.current = requestAnimationFrame(frame.current);
    }
  }, [level, peak]);

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    reduce.current = query?.matches ?? false;
    const follow = (e: MediaQueryListEvent) => {
      reduce.current = e.matches;
    };
    query?.addEventListener("change", follow);
    return () => {
      query?.removeEventListener("change", follow);
      if (frameId.current !== null) cancelAnimationFrame(frameId.current);
      frameId.current = null;
    };
  }, []);
}
