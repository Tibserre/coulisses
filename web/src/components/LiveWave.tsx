import { useEffect, useRef } from "react";
import { Mic, Star, X } from "lucide-react";
import type { Marker, TimedNote } from "../api.ts";
import type { MicEvent } from "../microphones.ts";
import { formatClock } from "../format.ts";
import { liveSegments, shownElapsed } from "../liveStrip.ts";
import { KIND_LABEL } from "../transcript.ts";
import { liveHeights, waveBars, WAVE } from "../liveWave.ts";

/** The recording as it goes by (D5a): the level heard, twenty pixels a second, the present at
 *  the right (its last four tenths of a second, as heard), the past leaving on the left; on it, the mode in force, the key moments and
 *  the annotations, at their time, leaving with it. Drawn at the screen's pace as the strip
 *  is (LiveStrip): the service gives the time and the level ten times a second, the frame
 *  moves on between two (display only, P2). Paused, or with reduced motion, it stays still.
 *  A key moment or an annotation still in sight is taken back by its cross. The
 *  microphones added, cut, back or taken away are small grey marks (spec §7.2). */
export function LiveWave({
  elapsed,
  rmsDb,
  paused,
  markers,
  notes,
  events,
  draftAt,
  onRemoveMarker,
  onRemoveNote,
}: {
  elapsed: number;
  rmsDb: number;
  paused: boolean;
  markers: Marker[];
  notes: TimedNote[];
  events: MicEvent[];
  /** An annotation being typed: its bead, at the time of its first letter. */
  draftAt: number | null;
  onRemoveMarker: (m: Marker) => void;
  onRemoveNote: (n: TimedNote) => void;
}) {
  // shortcut: the levels are those heard since this page opened (the service keeps no
  // history of them); left and come back, the wave starts again from there.
  const levels = useRef(new Map<number, number>());
  /** The last four levels received (one a tenth of a second): the present, as it sounds. */
  const recent = useRef<number[]>([]);
  const received = useRef({ elapsed, at: performance.now(), paused });
  if (received.current.elapsed !== elapsed || received.current.paused !== paused) {
    // Paused or resumed: what was heard before is not the present any more.
    if (received.current.paused !== paused) recent.current = [];
    received.current = { elapsed, at: performance.now(), paused };
    if (!paused) {
      const bar = Math.floor(elapsed / WAVE.secondsPerBar);
      levels.current.set(bar, Math.max(levels.current.get(bar) ?? -Infinity, rmsDb));
      recent.current = [...recent.current.slice(-3), rmsDb];
    }
  }
  const canvas = useRef<HTMLCanvasElement>(null);
  const placed = useRef<(HTMLElement | null)[]>([]);
  const lines = useRef<(HTMLElement | null)[]>([]);
  const labels = useRef<(HTMLElement | null)[]>([]);
  const draft = useRef<HTMLSpanElement>(null);
  const marks = useRef<(HTMLElement | null)[]>([]);
  const live = useRef({ markers, notes, events, draftAt });
  live.current = { markers, notes, events, draftAt };
  const frameId = useRef<number | null>(null);
  const start = useRef<() => void>(() => undefined);

  const moments = markers.filter((m) => m.kind === "key_moment");
  const sortedNotes = [...notes].sort((a, b) => a.at_s - b.at_s);
  const segments = liveSegments(markers, elapsed).filter((s) => s.kind !== "none");

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
      const x = (t: number) => WAVE.nowX - (shown - t) * WAVE.pxPerSecond;
      const { markers: ms, notes: ns, events: es, draftAt: d } = live.current;
      const momentsNow = ms.filter((m) => m.kind === "key_moment").map((m) => m.at_s);
      draw(canvas.current, waveBars(levels.current, shown, momentsNow));
      // The mode lines, the moments, the beads and their labels, moved at each frame.
      let k = 0;
      for (const s of liveSegments(ms, shown).filter((s) => s.kind !== "none")) {
        const el = lines.current[k++];
        if (!el) continue;
        const from = Math.max(0, x(s.start));
        el.style.left = `${from}px`;
        el.style.width = `${Math.max(0, x(s.end) - from)}px`;
      }
      let p = 0;
      for (const m of ms.filter((m) => m.kind === "key_moment")) {
        const el = placed.current[p++];
        if (el) el.style.transform = `translateX(${x(m.at_s)}px)`;
      }
      const sorted = [...ns].sort((a, b) => a.at_s - b.at_s);
      sorted.forEach((n, i) => {
        const el = placed.current[p + i];
        if (el) el.style.transform = `translateX(${x(n.at_s)}px)`;
        const label = labels.current[i];
        // Two close: the newer one is cut short of the older one's stem (all of it on hovering).
        const room = i === 0 ? x(n.at_s) : x(n.at_s) - x(sorted[i - 1].at_s) - 12;
        if (label) label.style.maxWidth = `${Math.max(0, room)}px`;
      });
      es.forEach((e, i) => {
        const el = marks.current[i];
        if (el) el.style.transform = `translateX(${x(e.at)}px)`;
      });
      if (draft.current && d !== null) draft.current.style.transform = `translateX(${x(d)}px)`;
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

  useEffect(() => {
    start.current();
  }, [elapsed, paused, markers, notes, events, draftAt]);

  return (
    <div className="cl-wave" data-paused={paused || undefined}>
      <div className="cl-wave__clip">
        <canvas ref={canvas} className="cl-wave__canvas" aria-hidden />
        {segments.map((s, k) => (
          <span
            key={`${s.kind}${s.start}`}
            ref={(el) => {
              lines.current[k] = el;
            }}
            className="cl-wave__mode"
            data-kind={s.kind}
          >
            <span className="cl-wave__modelabel">{KIND_LABEL[s.kind as "scene" | "discussion"]}</span>
          </span>
        ))}
        {events.map((e, k) => (
          <span
            key={e.key}
            ref={(el) => {
              marks.current[k] = el;
            }}
            className="cl-wave__event"
            title={`${formatClock(e.at)} ${e.text}`}
          >
            <Mic size={11} strokeWidth={2} aria-hidden />
            <span className="cl-sr">
              {formatClock(e.at)} {e.text}
            </span>
          </span>
        ))}
        {moments.map((m, k) => (
          <span
            key={`m${m.id}`}
            ref={(el) => {
              placed.current[k] = el;
            }}
            className="cl-wave__moment"
          >
            <Star size={14} fill="currentColor" stroke="none" aria-hidden />
            <button
              type="button"
              className="cl-wave__remove"
              aria-label={`Retirer le moment clé de ${formatClock(m.at_s)}`}
              title="Retirer"
              onClick={() => onRemoveMarker(m)}
            >
              <X size={12} strokeWidth={2} />
            </button>
          </span>
        ))}
        {sortedNotes.map((n, i) => (
          <span
            key={`n${n.id}`}
            ref={(el) => {
              placed.current[moments.length + i] = el;
            }}
            className="cl-wave__note"
          >
            <span className="cl-wave__bead" aria-hidden />
            <span className="cl-wave__stem" aria-hidden />
            <span
              className="cl-wave__label"
              ref={(el) => {
                labels.current[i] = el;
              }}
              title={`${formatClock(n.at_s)} ${n.text}`}
            >
              <b>{formatClock(n.at_s)}</b>
              {n.text}
            </span>
            <button
              type="button"
              className="cl-wave__remove"
              aria-label={`Retirer l'annotation de ${formatClock(n.at_s)}`}
              title="Retirer"
              onClick={() => onRemoveNote(n)}
            >
              <X size={12} strokeWidth={2} />
            </button>
          </span>
        ))}
        {draftAt !== null && (
          <span ref={draft} className="cl-wave__note" data-draft>
            <span className="cl-wave__bead" aria-hidden />
          </span>
        )}
      </div>
      {!paused && (
        <span className="cl-wave__live" aria-hidden>
          {liveHeights(recent.current).map((h, k) => (
            <i key={k} style={{ height: `${h}px` }} />
          ))}
        </span>
      )}
      <span className="cl-wave__now" aria-hidden />
      <span className="cl-wave__future" aria-hidden />
    </div>
  );
}

/** The bars, on a canvas sized to its box and to the screen's pixels. */
function draw(canvas: HTMLCanvasElement | null, bars: ReturnType<typeof waveBars>) {
  if (!canvas) return;
  const ratio = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
  }
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const style = getComputedStyle(canvas);
  const quiet = style.getPropertyValue("--cl-wave-ink").trim() || "rgba(0,0,0,.32)";
  const marked = style.getPropertyValue("--cl-wave-mark").trim() || "#a63d1e";
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  const mid = WAVE.midY;
  for (const bar of bars) {
    const half = Math.max(1.5, bar.height * WAVE.maxHalf);
    ctx.strokeStyle = bar.marked ? marked : quiet;
    ctx.beginPath();
    ctx.moveTo(bar.x, mid - half);
    ctx.lineTo(bar.x, mid + half);
    ctx.stroke();
  }
}
