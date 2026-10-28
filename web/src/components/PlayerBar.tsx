import { memo, useEffect } from "react";
import { IconButton } from "@astryxdesign/core/IconButton";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core/SegmentedControl";
import { Text } from "@astryxdesign/core/Text";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { formatClock } from "../format.ts";
import type { ReviewModel, TurnRow } from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";

const RATES = ["0.75", "1", "1.25", "1.5", "2"];

/** Keys typed into a field or on a control keep their usual meaning. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A"].includes(target.tagName) ||
    target.closest(
      '[role="button"], [role="slider"], [role="radio"], [role="tab"], dialog',
    ) !== null
  );
}

/** Previous line, play, next line, position, speed. Space plays or pauses; the arrows
 *  move from line to line. */
export function PlayerBar({
  model,
  pb,
  current,
  marks = [],
  markInk,
  keys = true,
}: {
  model: ReviewModel;
  pb: Playback;
  current: TurnRow | null;
  /** Where a voice speaks (the one shown, or pointed at), marked on the position bar. */
  marks?: { start: number; end: number }[];
  markInk?: string;
  /** Its keys (Space, the arrows); off while naming, guided: the page is out of reach. */
  keys?: boolean;
}) {
  const timed = model.timed;
  const position = current ? timed.indexOf(current) : -1;

  const previous = () => {
    // Back to the start of the line being heard if it began more than 2 s ago.
    const start = current?.turn.start;
    if (start != null && pb.time - start > 2) pb.seek(start);
    else if (position > 0) pb.seek(timed[position - 1].turn.start ?? 0);
    else if (timed.length) pb.seek(timed[0].turn.start ?? 0);
  };
  const next = () => {
    const target = timed.find((r) => (r.turn.start ?? 0) > pb.time + 0.05);
    if (target?.turn.start != null) pb.seek(target.turn.start);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!keys || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey)
        return;
      if (e.code === "Space") {
        e.preventDefault();
        pb.toggle();
      } else if (e.code === "ArrowLeft" || e.code === "ArrowUp") {
        e.preventDefault();
        previous();
      } else if (e.code === "ArrowRight" || e.code === "ArrowDown") {
        e.preventDefault();
        next();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <footer className="cl-player">
      <div className="cl-player__controls">
        <IconButton
          label="Réplique précédente (←)"
          icon={<SkipBack size={18} strokeWidth={1.75} />}
          variant="ghost"
          onClick={previous}
        />
        <IconButton
          label={pb.playing ? "Pause (espace)" : "Lecture (espace)"}
          icon={
            pb.playing ? (
              <Pause size={20} strokeWidth={1.75} />
            ) : (
              <Play size={20} strokeWidth={1.75} />
            )
          }
          variant="primary"
          size="lg"
          onClick={pb.toggle}
        />
        <IconButton
          label="Réplique suivante (→)"
          icon={<SkipForward size={18} strokeWidth={1.75} />}
          variant="ghost"
          onClick={next}
        />
      </div>
      <Text type="supporting">
        {formatClock(pb.time)} /{" "}
        {pb.duration != null ? formatClock(pb.duration) : "—"}
      </Text>
      <span className="cl-player__track">
        <input
          className="cl-player__seek"
          type="range"
          min={0}
          max={pb.duration ?? 0}
          step={0.1}
          value={pb.time}
          onChange={(e) => pb.seek(Number(e.target.value), pb.playing)}
          aria-label="Position dans l'enregistrement"
        />
        {pb.duration != null && marks.length > 0 && (
          <Marks
            marks={marks}
            duration={pb.duration}
            ink={markInk}
            seek={pb.seek}
          />
        )}
      </span>
      <SegmentedControl
        label="Vitesse de lecture"
        value={String(pb.rate)}
        onChange={(v: string) => pb.setRate(Number(v))}
        size="sm"
      >
        {RATES.map((r) => (
          <SegmentedControlItem
            key={r}
            value={r}
            label={`${r.replace(".", ",")}×`}
          />
        ))}
      </SegmentedControl>
      {pb.error && (
        <Text type="supporting" color="primary">
          {pb.error}
        </Text>
      )}
    </footer>
  );
}

/** Where a voice speaks, on the position bar: drawn once per voice, not at each frame of
 *  playback (a talkative voice has hundreds of lines). */
const Marks = memo(function Marks({
  marks,
  duration,
  ink,
  seek,
}: {
  marks: { start: number; end: number }[];
  duration: number;
  ink?: string;
  seek: (t: number) => void;
}) {
  return (
    <span className="cl-player__marks" style={{ color: ink }}>
      {marks.map((m) => (
        <button
          key={m.start}
          type="button"
          tabIndex={-1}
          className="cl-player__mark"
          aria-label={`Aller à ${formatClock(m.start)}`}
          style={{
            left: `${(100 * m.start) / duration}%`,
            width: `max(2px, ${(100 * (m.end - m.start)) / duration}%)`,
          }}
          onClick={() => seek(m.start)}
        />
      ))}
    </span>
  );
});
