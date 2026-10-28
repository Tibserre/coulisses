import { ChevronLeft, ChevronRight, X } from "lucide-react";
import type { Speaker } from "../api.ts";
import { formatDuration, plural } from "../format.ts";
import type { ReviewModel, TurnRow } from "../transcript.ts";
import { speakerTitle } from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";
import { inkOf } from "./TranscriptView.tsx";

/** Above the transcript while it shows one voice only: which, how much it says, its lines
 *  one after the other (‹ ›, as the player's arrows), naming it, and back to all (✕ or
 *  Escape). */
export function SpeakerFocusBar({
  speaker,
  shown,
  pb,
  current,
  onName,
  onClose,
}: {
  speaker: Speaker;
  /** The transcript as shown: this voice's lines only. */
  shown: ReviewModel;
  pb: Playback;
  current: TurnRow | null;
  onName: () => void;
  onClose: () => void;
}) {
  const lines = shown.timed;
  const at = current ? lines.indexOf(current) : -1;
  const previous = () => {
    const target = [...lines]
      .reverse()
      .find((r) => (r.turn.start ?? 0) < pb.time - 0.5);
    if (target?.turn.start != null) pb.seek(target.turn.start);
  };
  const next = () => {
    const target = lines.find((r) => (r.turn.start ?? 0) > pb.time + 0.05);
    if (target?.turn.start != null) pb.seek(target.turn.start);
  };
  return (
    <div
      className="cl-focusbar"
      role="region"
      aria-label={`Répliques de ${speaker.name}`}
    >
      <span
        className="cl-dot"
        style={{ background: inkOf(speaker) }}
        aria-hidden
      />
      <span className="cl-focusbar__name">{speakerTitle(speaker)}</span>
      <span className="cl-focusbar__meta">
        {plural(speaker.turns, "réplique", "répliques")} ·{" "}
        {formatDuration(speaker.seconds)}
      </span>
      <span className="cl-focusbar__nav">
        <button
          type="button"
          className="cl-iconbtn"
          aria-label="Sa réplique précédente"
          onClick={previous}
        >
          <ChevronLeft size={16} strokeWidth={1.75} />
        </button>
        <span className="cl-focusbar__count">
          {at >= 0 ? `${at + 1} / ${lines.length}` : `— / ${lines.length}`}
        </span>
        <button
          type="button"
          className="cl-iconbtn"
          aria-label="Sa réplique suivante"
          onClick={next}
        >
          <ChevronRight size={16} strokeWidth={1.75} />
        </button>
      </span>
      <button type="button" className="cl-linkbtn" onClick={onName}>
        {speaker.named ? "Renommer" : "Nommer"}
      </button>
      <button
        type="button"
        className="cl-iconbtn"
        aria-label="Revenir à toutes les voix (Échap)"
        title="Toutes les voix (Échap)"
        onClick={onClose}
      >
        <X size={16} strokeWidth={1.75} />
      </button>
    </div>
  );
}
