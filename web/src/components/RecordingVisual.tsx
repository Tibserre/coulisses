import { useRef } from "react";
import { useNeedle } from "../useNeedle.ts";

const RINGS = [0, 1, 2];

/** The place of `enregistrement.riv` (art direction): until the file is drawn, a stand-in
 *  made in code, with the same inputs. `niveau` 0 to 100, `pause`. Rings widen with the
 *  level, smoothly, at the screen's pace; paused, they rest. Ink and brick only, a 1.75
 *  stroke, no background. */
export function RecordingVisual({ niveau, pause }: { niveau: number; pause: boolean }) {
  const rings = useRef<(SVGCircleElement | null)[]>([]);
  const core = useRef<SVGCircleElement>(null);
  useNeedle(pause ? 0 : niveau, 0, ({ level }) => {
    const l = Math.max(0, Math.min(100, level)) / 100;
    rings.current.forEach((ring, k) => ring?.setAttribute("r", String(34 + k * 18 + l * (14 + k * 10))));
    core.current?.setAttribute("r", String(pause ? 24 : 26 + l * 6));
  });
  return (
    <svg className="cl-recvisual" viewBox="0 0 200 200" role="img" aria-hidden data-paused={pause || undefined}>
      {RINGS.map((k) => (
        <circle
          key={k}
          ref={(el) => {
            rings.current[k] = el;
          }}
          cx="100"
          cy="100"
          r={34 + k * 18}
          className="cl-recvisual__ring"
          style={{ opacity: pause ? 0.18 : 0.55 - k * 0.15 }}
        />
      ))}
      <circle ref={core} cx="100" cy="100" r={26} className="cl-recvisual__core" />
    </svg>
  );
}
