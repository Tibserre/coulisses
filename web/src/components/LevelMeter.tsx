import { useRef } from "react";
import { useNeedle } from "../useNeedle.ts";

/** The input meter: the level, smoothed like a needle, and the peak as a thin mark that
 *  holds a moment then falls. Brick when it saturates. */
export function LevelMeter({ level, peak, clipping }: { level: number; peak: number; clipping: boolean }) {
  const bar = useRef<HTMLSpanElement>(null);
  const mark = useRef<HTMLSpanElement>(null);
  useNeedle(level, peak, (needle) => {
    if (bar.current) bar.current.style.width = `${needle.level}%`;
    if (mark.current) mark.current.style.left = `${needle.peak}%`;
  });
  return (
    <div
      className="cl-meter"
      role="meter"
      aria-label="Niveau d'entrée"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(level)}
      data-clipping={clipping || undefined}
    >
      <span ref={bar} className="cl-meter__level" />
      <span ref={mark} className="cl-meter__peak" />
    </div>
  );
}
