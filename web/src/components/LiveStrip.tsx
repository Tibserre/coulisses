import { useEffect, useRef } from "react";
import type { Marker } from "../api.ts";
import { formatClock } from "../format.ts";
import { liveSegments, shownElapsed } from "../liveStrip.ts";

/** The chapters as they are marked, growing with the recording at the screen's pace: the
 *  service gives the time ten times a second, and a strip redrawn only then jumps. The
 *  segments and key moments are placed at each frame, straight in the DOM; React only
 *  says how many there are and of which kind. Paused, or with reduced motion, the loop
 *  places them once and stops until the next time given. */
export function LiveStrip({ markers, elapsed, paused }: { markers: Marker[]; elapsed: number; paused: boolean }) {
  // When the service last gave the time: only a new time (or a pause) resets it, not any
  // render of the page (typing a note re-renders it too).
  const received = useRef({ elapsed, at: performance.now(), paused });
  if (received.current.elapsed !== elapsed || received.current.paused !== paused) {
    received.current = { elapsed, at: performance.now(), paused };
  }
  const segmentsRef = useRef<(HTMLSpanElement | null)[]>([]);
  const momentsRef = useRef<(HTMLSpanElement | null)[]>([]);
  const markersRef = useRef(markers);
  markersRef.current = markers;
  const frameId = useRef<number | null>(null);
  const start = useRef<() => void>(() => undefined);

  const segments = liveSegments(markers, elapsed);
  const moments = markers.filter((m) => m.kind === "key_moment");

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let reduce = query?.matches ?? false;
    const follow = (e: MediaQueryListEvent) => {
      reduce = e.matches;
      start.current();
    };
    query?.addEventListener("change", follow);
    let lastShown = 0;
    const frame = (now: number) => {
      const { elapsed: given, at, paused: still } = received.current;
      const shown = shownElapsed(given, (now - at) / 1000, lastShown, still || reduce);
      lastShown = shown;
      const span = Math.max(shown, 1);
      liveSegments(markersRef.current, shown).forEach((s, k) => {
        const el = segmentsRef.current[k];
        if (!el) return;
        el.style.left = `${(s.start / span) * 100}%`;
        el.style.width = `${((s.end - s.start) / span) * 100}%`;
      });
      markersRef.current
        .filter((m) => m.kind === "key_moment")
        .forEach((m, k) => {
          const el = momentsRef.current[k];
          if (el) el.style.left = `${(m.at_s / span) * 100}%`;
        });
      // Still: placed, nothing more moves until the service gives something new.
      frameId.current = still || reduce ? null : requestAnimationFrame(frame);
    };
    start.current = () => {
      if (frameId.current === null) frameId.current = requestAnimationFrame(frame);
    };
    start.current();
    return () => {
      query?.removeEventListener("change", follow);
      if (frameId.current !== null) cancelAnimationFrame(frameId.current);
      frameId.current = null;
    };
  }, []);

  // Something new (a time, a pause or a resume, a marker): placed again.
  useEffect(() => {
    start.current();
  }, [elapsed, paused, markers]);

  return (
    <div className="cl-live__bar">
      {segments.map((s, k) => (
        <span
          key={`${s.kind}${s.start}`}
          ref={(el) => {
            segmentsRef.current[k] = el;
          }}
          className="cl-live__segment"
          data-kind={s.kind}
        />
      ))}
      {moments.map((m, k) => (
        <span
          key={m.id}
          ref={(el) => {
            momentsRef.current[k] = el;
          }}
          className="cl-live__moment"
          title={`Moment clé à ${formatClock(m.at_s)}`}
        />
      ))}
    </div>
  );
}
