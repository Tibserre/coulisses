import { useMemo } from "react";
import { Heading } from "@astryxdesign/core/Heading";
import { Check, ChevronLeft, ChevronRight, Pause, Play, X } from "lucide-react";
import type { EditRequest, Speaker } from "../api.ts";
import { formatDuration, plural } from "../format.ts";
import type { ReviewModel, TurnRow } from "../transcript.ts";
import { speakerTitle, speakerExcerpt } from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";
import { speakerInk } from "../theme/shared.ts";
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
  onCorrect,
  onPoint,
  dev,
  problem,
}: {
  model: ReviewModel;
  pb: Playback;
  /** The audio deleted: nothing to hear. */
  audioGone: boolean;
  onShow: (label: string) => void;
  /** Shows its lines only, and names it there. */
  onName: (label: string, turn: number) => void;
  /** « Oui » and « Non » to a recognised voice; a refusal is said by the page. */
  onCorrect: (correction: EditRequest) => Promise<void>;
  onPoint: (label: string | null) => void;
  /** Developer mode: how close the voice is to the profile. */
  dev: boolean;
  /** Why some voices could not be compared (P8). */
  problem?: string | null;
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
  const name = (label: string, line: TurnRow | null | undefined) => {
    const first = line ?? model.timed.find((r) => r.speaker.label === label);
    if (first) onName(label, first.turn.index);
  };
  return (
    <section>
      <Heading level={3}>À nommer</Heading>
      {problem && <p className="cl-toname__problem">{problem}</p>}
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
                onClick={() => name(s.label!, line)}
              >
                Nommer
              </button>
              {s.proposal && (
                <span className="cl-toname__guess">
                  C'est{" "}
                  <button
                    type="button"
                    className="cl-toname__who"
                    style={{ color: speakerInk(s.proposal.color_slot) }}
                    title="Choisir dans la liste des personnes"
                    onClick={() => name(s.label!, line)}
                  >
                    {s.proposal.name}
                  </button>{" "}
                  ?
                  <button
                    type="button"
                    className="cl-iconbtn"
                    aria-label={`Oui, c'est ${s.proposal.name}`}
                    title={`Oui, c'est ${s.proposal.name}`}
                    onClick={() =>
                      void onCorrect({
                        kind: "assign_speaker",
                        speaker: s.label!,
                        person_id: s.proposal!.person_id,
                      }).catch(() => {}) // the page already says why it was refused
                    }
                  >
                    <Check size={14} strokeWidth={2} />
                  </button>
                  <button
                    type="button"
                    className="cl-iconbtn"
                    aria-label={`Non, ce n'est pas ${s.proposal.name}`}
                    title={`Non, ce n'est pas ${s.proposal.name}`}
                    onClick={() =>
                      void onCorrect({
                        kind: "reject_voice_match",
                        speaker: s.label!,
                        person_id: s.proposal!.person_id,
                      }).catch(() => {}) // the page already says why it was refused
                    }
                  >
                    <X size={14} strokeWidth={2} />
                  </button>
                  {dev && (
                    <span className="cl-toname__time">
                      distance {s.proposal.distance.toFixed(3)}
                    </span>
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
