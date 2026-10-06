import { useEffect, useRef } from "react";

const RINGS = 3;
/** Seconds for a ring to travel from the centre to the edge: a steady, unhurried pace. */
const PERIOD_S = 2.6;
const INNER = 30;
const OUTER = 96;
/** How slowly the shown intensity follows the level, rising and falling (seconds). */
const LEVEL_RISE_S = 0.25;
const LEVEL_FALL_S = 0.6;
const PAUSE_FADE_S = 0.4;

/** The place of `enregistrement.riv` (art direction): until the file is drawn, a stand-in
 *  made in code, with the same inputs, `niveau` 0 to 100 and `pause`.
 *
 *  Rings leave the centre and widen at a constant pace, like ripples: the motion is always
 *  smooth. The level only sets how strongly they show (smoothed over half a second), never
 *  their size (smoothed, 0.25 s rising, 0.6 s falling): speech changes too fast for a size
 *  to follow it without jerking. Paused,
 *  the rings stop and fade, and the loop ends. With reduced motion, they stay still and
 *  only their strength follows the level, at once. Ink and brick only, a 1.75 stroke. */
export function RecordingVisual({
  niveau,
  pause,
}: {
  niveau: number;
  pause: boolean;
}) {
  const rings = useRef<(SVGCircleElement | null)[]>([]);
  const core = useRef<SVGCircleElement>(null);
  const input = useRef({ niveau, pause });
  input.current = { niveau, pause };
  const frameId = useRef<number | null>(null);
  const run = useRef<() => void>(() => undefined);

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let reduce = query?.matches ?? false;
    const follow = (e: MediaQueryListEvent) => {
      reduce = e.matches;
    };
    query?.addEventListener("change", follow);

    let phase = 0; // seconds of travel, frozen while paused
    let strength = 0; // 0 to 1, the smoothed level
    let presence = 1; // 1 while recording, fades to a rest while paused
    let last = performance.now();

    const frame = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const { niveau: level, pause: paused } = input.current;
      const target = paused ? 0 : Math.max(0, Math.min(100, level)) / 100;
      const tau = target > strength ? LEVEL_RISE_S : LEVEL_FALL_S;
      strength = reduce ? target : strength + (target - strength) * (1 - Math.exp(-dt / tau));
      presence +=
        ((paused ? 0.25 : 1) - presence) * (1 - Math.exp(-dt / PAUSE_FADE_S));
      if (!paused && !reduce) phase += dt;

      rings.current.forEach((ring, k) => {
        if (!ring) return;
        // Still rings with reduced motion; otherwise each one travels, a third apart.
        const p = reduce
          ? (k + 1) / (RINGS + 1)
          : (phase / PERIOD_S + k / RINGS) % 1;
        const radius = INNER + p * (OUTER - INNER);
        const fade = reduce ? 1 - p * 0.6 : Math.sin(Math.PI * p); // in, then out: no pop
        ring.setAttribute("r", radius.toFixed(2));
        ring.setAttribute(
          "opacity",
          (fade * presence * (0.18 + 0.72 * strength)).toFixed(3),
        );
      });
      core.current?.setAttribute(
        "r",
        (24 + 5 * strength * presence).toFixed(2),
      );

      // Settled while paused (or still, with reduced motion and a steady level): stop.
      const resting =
        (paused || reduce) &&
        Math.abs(target - strength) < 0.002 &&
        Math.abs((paused ? 0.25 : 1) - presence) < 0.002;
      frameId.current = resting ? null : requestAnimationFrame(frame);
    };

    run.current = () => {
      if (frameId.current === null) {
        last = performance.now();
        frameId.current = requestAnimationFrame(frame);
      }
    };
    run.current();
    return () => {
      query?.removeEventListener("change", follow);
      if (frameId.current !== null) cancelAnimationFrame(frameId.current);
      frameId.current = null;
    };
  }, []);

  // A new level or a resume wakes the loop if it had come to rest.
  useEffect(() => {
    run.current();
  }, [niveau, pause]);

  return (
    <svg
      className="cl-recvisual"
      viewBox="0 0 200 200"
      role="img"
      aria-hidden
      data-paused={pause || undefined}
    >
      {Array.from({ length: RINGS }, (_, k) => (
        <circle
          key={k}
          ref={(el) => {
            rings.current[k] = el;
          }}
          cx="100"
          cy="100"
          r={INNER}
          opacity={0}
          className="cl-recvisual__ring"
        />
      ))}
      <circle
        ref={core}
        cx="100"
        cy="100"
        r={24}
        className="cl-recvisual__core"
      />
    </svg>
  );
}
