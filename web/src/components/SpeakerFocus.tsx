import { useMemo } from "react";
import { Heading } from "@astryxdesign/core/Heading";
import { ChevronLeft, ChevronRight, Pause, Play, X } from "lucide-react";
import type { Speaker } from "../api.ts";
import { formatDuration, plural } from "../format.ts";
import type { ReviewModel, TurnRow } from "../transcript.ts";
import { speakerTitle, speakerExcerpt } from "../transcript.ts";
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

/** The voices not named yet, to recognise them without searching: how long each speaks,
 *  its longest line quoted, a few seconds of it to hear (▶), « Nommer » there. A click on
 *  a voice shows its lines only; pointing at it marks where it speaks on the player bar. */
export function SpeakersToName({
  model,
  pb,
  audioGone,
  onShow,
  onName,
  onPoint,
}: {
  model: ReviewModel;
  pb: Playback;
  /** The audio deleted: nothing to hear. */
  audioGone: boolean;
  onShow: (label: string) => void;
  /** Shows its lines only, and names it there. */
  onName: (label: string, turn: number) => void;
  onPoint: (label: string | null) => void;
}) {
  // Read once per version, not at each frame of playback (two hours, many voices: P3).
  const unnamed = useMemo(
    () =>
      model.speakers
        .filter((s) => !s.named && s.label !== null)
        .map((s) => {
          const line = speakerExcerpt(model, s.label!);
          return { s, line, quote: line?.turn.words.map((w) => w.text).join(" ") };
        }),
    [model],
  );
  if (unnamed.length === 0) return null;
  return (
    <section>
      <Heading level={3}>À nommer</Heading>
      <ul className="cl-toname">
        {unnamed.map(({ s, line, quote }) => {
          const heard = line != null && pb.excerpt === line.turn.start && pb.playing;
          return (
            <li
              key={s.label}
              onPointerEnter={() => onPoint(s.label)}
              onPointerLeave={() => onPoint(null)}
              onFocus={() => onPoint(s.label)}
              onBlur={() => onPoint(null)}
            >
              {!audioGone &&
              line &&
              line.turn.start != null &&
              line.turn.end != null ? (
                <button
                  type="button"
                  className="cl-iconbtn"
                  aria-label={
                    heard
                      ? `Arrêter l'extrait de ${s.name}`
                      : `Écouter ${s.name} quelques secondes`
                  }
                  onClick={() => pb.listen(line.turn.start!, line.turn.end!)}
                >
                  {heard ? (
                    <Pause size={14} strokeWidth={2} />
                  ) : (
                    <Play size={14} strokeWidth={2} />
                  )}
                </button>
              ) : (
                <span className="cl-toname__noplay" aria-hidden />
              )}
              <button
                type="button"
                className="cl-toname__voice"
                title={`N'afficher que les répliques de ${s.name}`}
                onClick={() => onShow(s.label!)}
              >
                <span className="cl-toname__name">
                  {s.name}
                  <span className="cl-toname__time">
                    {formatDuration(s.seconds)}
                  </span>
                </span>
                {quote && <span className="cl-toname__quote">« {quote} »</span>}
              </button>
              <button
                type="button"
                className="cl-linkbtn"
                onClick={() => {
                  const first =
                    line ??
                    model.timed.find((r) => r.speaker.label === s.label);
                  if (first) onName(s.label!, first.turn.index);
                }}
              >
                Nommer
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
