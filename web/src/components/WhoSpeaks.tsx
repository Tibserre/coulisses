import { useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Popover } from "@astryxdesign/core/Popover";
import { ChevronLeft, ChevronRight, Pause, Play, User } from "lucide-react";
import {
  api,
  type EditRequest,
  type Person,
  type Speaker,
  type Turn,
} from "../api.ts";
import { formatDuration, plural } from "../format.ts";
import { speakerInk, speakerTint } from "../theme/shared.ts";
import {
  hasVoice,
  namingLines,
  nearestLine,
  speechWave,
  whoOrder,
  type TurnRow,
} from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";
import { Face, PeoplePicker } from "./AttendeesSheet.tsx";

/** Bars of the session's wave. */
const BARS = 72;
/** Named voices shown in the pile; the others go into its « +N ». */
const PILE = 8;

const initial = (name: string) => name.trim().charAt(0).toLocaleUpperCase("fr");

/** A voice's disc: its person's face, else its initial in its colour (a free name, a
 *  character), else an empty place. */
function VoiceFace({
  voice,
  people,
  size = "md",
}: {
  voice: Speaker;
  people: Person[];
  size?: "sm" | "md" | "lg";
}) {
  const person = people.find((p) => p.id === voice.person_id);
  if (person && !voice.character) return <Face person={person} size={size} />;
  if (!voice.named) return <Face size={size} />;
  return (
    <span
      className="cl-face"
      data-size={size}
      style={{
        background: speakerTint(voice.color_slot ?? 0),
        color: speakerInk(voice.color_slot ?? 0),
      }}
      aria-hidden
    >
      {initial(voice.name)}
    </span>
  );
}

/** « Qui parle ? » (ADR 0090): one voice at a time, the most talkative first. On the left,
 *  one listens: the voice's big ring (the face of the person chosen), its line in large with
 *  ▶ and ‹ ›, the session's wave dark where it speaks. On the right, one chooses as in
 *  « Qui est là ? »; a new name is a guest. On top, the pile of the voices named and « +N »
 *  for the others: one button that lists them all. Times are the measured ones (P2); what
 *  cannot be heard is said (P8). */
export function WhoSpeaks({
  speaker,
  voices,
  toName,
  people,
  attendees,
  spaceName,
  lines,
  turns,
  duration,
  pb,
  audioGone,
  dev,
  notice,
  onGo,
  onSkip,
  onClose,
  onCorrect,
  onAddGuest,
  onPeopleChanged,
}: {
  speaker: Speaker;
  /** Every voice of the session. */
  voices: Speaker[];
  /** The voices without a name, in the order they are named. */
  toName: Speaker[];
  people: Person[];
  attendees: readonly number[];
  spaceName: string;
  /** The voice's lines, in their order. */
  lines: TurnRow[];
  /** All the lines of the session, for its wave. */
  turns: readonly Turn[];
  /** The session's length; 0 when unknown (then no wave). */
  duration: number;
  pb: Playback;
  audioGone: boolean;
  dev: boolean;
  /** Said once a naming has merged two voices (P3), with how to undo it. */
  notice: string | null;
  onGo: (label: string) => void;
  onSkip: () => void;
  onClose: () => void;
  onCorrect: (correction: EditRequest) => Promise<void>;
  onAddGuest: (name: string) => Promise<Person>;
  onPeopleChanged: () => Promise<void>;
}) {
  const label = speaker.label!;
  const proposed =
    people.find((p) => p.id === speaker.proposal?.person_id) ?? null;
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<Person | null>(proposed);
  const [at, setAt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [listing, setListing] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  // Each voice starts afresh: its recognised person chosen, its longest line shown.
  useEffect(() => {
    setQuery("");
    setPicked(proposed);
    setAt(0);
    setError(null);
    // The cursor in the search, once the dialog has put it on its title (its own effect).
    const t = window.setTimeout(() => body.current?.querySelector("input")?.focus(), 0);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per voice
  }, [label]);

  const longest = namingLines(lines, "long");
  const current = longest[Math.min(at, longest.length - 1)] ?? null;
  const hearing =
    current != null && pb.excerpt != null && pb.excerpt === current.turn.start;
  const silent = audioGone || current?.turn.start == null;
  const hear = (row: TurnRow | null) => {
    if (!row || audioGone) return;
    const { start, end } = row.turn;
    // The excerpt stops at its end, else after 8 s (usePlayback).
    if (start != null) pb.listen(start, end ?? Infinity);
    // Not to be heard: what was being heard stops.
    else if (pb.excerpt != null) pb.listen(pb.excerpt, pb.excerpt);
  };
  const move = (by: number) => {
    if (!longest.length) return;
    const next = (at + by + longest.length) % longest.length;
    setAt(next);
    hear(longest[next]);
  };

  const run = async (step: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await step();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const merges = picked != null && hasVoice(picked, speaker, voices);
  const confirm = (who: Person | null = picked) =>
    who &&
    void run(() =>
      onCorrect({
        kind: "assign_speaker",
        speaker: label,
        person_id: who.id,
      }),
    );
  /** « Ce n'est pas … » (ADR 0057): a correction like another, undone from the corrections. */
  const reject = () =>
    proposed &&
    void run(async () => {
      await onCorrect({
        kind: "reject_voice_match",
        speaker: label,
        person_id: proposed.id,
      });
      setPicked(null);
    });
  const addGuest = () =>
    void run(async () => {
      const guest = await onAddGuest(query.trim());
      setPicked(guest);
      setQuery("");
    });
  const makeMember = (p: Person) =>
    void run(async () => {
      await api.updatePerson(p.id, { kind: "member" });
      await onPeopleChanged();
    });

  const named = voices.filter((v) => v.named && v.label !== null);
  const pile = named.slice(0, PILE);
  // Those left to name, besides the one being named.
  const over = named.length - pile.length + toName.length - (speaker.named ? 0 : 1);
  const place = toName.indexOf(speaker);
  const number =
    (place < 0 ? 0 : place) + named.length + (speaker.named ? 0 : 1);
  const timed = lines.filter((r) => r.turn.start != null);
  const wave = duration > 0 ? speechWave(turns, label, duration, BARS) : [];
  const mark =
    current?.turn.start != null && duration > 0
      ? current.turn.start / duration
      : null;
  const chosen = picked;

  // ← → Space drive the listening, outside the search field.
  const onKeyDown = (e: React.KeyboardEvent) => {
    const t = e.target as HTMLElement;
    // In the search field, only while nothing is typed (then Space and the arrows type).
    if (t.tagName === "INPUT" && (t as HTMLInputElement).value !== "") return;
    if (t.tagName === "INPUT" && e.key === "Enter") return;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      move(-1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      move(1);
    } else if (e.key === " " && t.tagName !== "BUTTON") {
      e.preventDefault();
      hear(current);
    } else if (e.key === "Enter" && t.tagName !== "BUTTON") {
      e.preventDefault();
      confirm();
    }
  };

  const voiceRow = (v: Speaker) => (
    <li key={v.label}>
      <button
        type="button"
        className="cl-spacepick__item"
        aria-current={v.label === label || undefined}
        onClick={() => {
          setListing(false);
          if (v.label) onGo(v.label);
        }}
      >
        <VoiceFace voice={v} people={people} size="sm" />
        <span className="cl-spacepick__what">{v.name}</span>
        <span className="cl-who__time">{formatDuration(v.seconds)}</span>
      </button>
    </li>
  );

  return (
    <Dialog
      isOpen
      onOpenChange={(open) => !open && onClose()}
      width={920}
      aria-label="Qui parle ?"
    >
      <div ref={body} onKeyDown={onKeyDown}>
      <DialogHeader
        title={
          <span className="cl-who__title">
            Qui parle ?
          <Popover
            isOpen={listing}
            onOpenChange={setListing}
            label="Les voix de la séance"
            placement="below"
            alignment="start"
            width={280}
            padding={1}
            content={
              <ul className="cl-spacepick" aria-label="Les voix de la séance">
                {[speaker, ...toName.filter((v) => v !== speaker)]
                  .filter((v) => !v.named)
                  .map(voiceRow)}
                {named.length > 0 && toName.length > 0 && (
                  <li className="cl-who__rule" aria-hidden />
                )}
                {named.map(voiceRow)}
              </ul>
            }
          >
            <button
              type="button"
              className="cl-who__pile"
              aria-label={`${plural(named.length, "voix nommée", "voix nommées")}, ${plural(toName.length, "à nommer", "à nommer")}. Voir les voix`}
            >
              <span className="cl-faces">
                {pile.map((v) => (
                  <VoiceFace
                    key={v.label}
                    voice={v}
                    people={people}
                    size="sm"
                  />
                ))}
                {over > 0 && (
                  <span className="cl-face" data-over aria-hidden>
                    +{over}
                  </span>
                )}
              </span>
            </button>
          </Popover>
          </span>
        }
        onOpenChange={onClose}
      />
      <div className="cl-who">
        <div className="cl-who__hear">
          <div className="cl-who__voice">
            <span
              className="cl-who__ring"
              data-chosen={chosen ? true : undefined}
            >
              {chosen ? (
                <Face person={chosen} size="lg" />
              ) : speaker.named ? (
                <VoiceFace voice={speaker} people={people} size="lg" />
              ) : (
                <span className="cl-who__empty" aria-hidden>
                  <User size={22} strokeWidth={1.5} />
                </span>
              )}
            </span>
            <span className="cl-who__id">
              <b>
                {speaker.named
                  ? speaker.name
                  : `Voix ${number} sur ${voices.filter((v) => v.label !== null).length}`}
              </b>
              <small>
                {speaker.seconds >= 1
                  ? `${formatDuration(speaker.seconds)} de parole · `
                  : ""}
                {plural(lines.length, "réplique", "répliques")}
                {dev && speaker.proposal
                  ? ` · distance ${speaker.proposal.distance.toFixed(3)}`
                  : ""}
              </small>
              {proposed && !speaker.named && (
                <button type="button" className="cl-linkbtn" onClick={reject}>
                  Ce n'est pas {proposed.name}
                </button>
              )}
            </span>
          </div>
          <p className="cl-who__line">
            {current?.turn.words.map((w) => w.text).join(" ")}
          </p>
          {/* What cannot be heard, said (P8). */}
          {audioGone ? (
            <p className="cl-who__said">
              L'audio de cette séance a été supprimé : les répliques se lisent,
              elles ne s'écoutent plus.
            </p>
          ) : (
            pb.error && (
              <p className="cl-who__said" role="alert">
                {pb.error}
              </p>
            )
          )}
          <div className="cl-who__controls">
            <button
              type="button"
              className="cl-who__step"
              aria-label="Réplique précédente (←)"
              disabled={longest.length < 2}
              onClick={() => move(-1)}
            >
              <ChevronLeft size={16} strokeWidth={1.75} />
            </button>
            <button
              type="button"
              className="cl-who__play"
              aria-label={
                hearing ? "Arrêter (Espace)" : "Écouter cette réplique (Espace)"
              }
              disabled={silent}
              onClick={() => hear(current)}
            >
              {hearing ? (
                <Pause size={20} fill="currentColor" />
              ) : (
                <Play size={20} fill="currentColor" />
              )}
            </button>
            <button
              type="button"
              className="cl-who__step"
              aria-label="Réplique suivante (→)"
              disabled={longest.length < 2}
              onClick={() => move(1)}
            >
              <ChevronRight size={16} strokeWidth={1.75} />
            </button>
            <span className="cl-who__count">
              Réplique {Math.min(at, longest.length - 1) + 1} sur{" "}
              {longest.length}
            </span>
          </div>
          {wave.length > 0 && (
            <button
              type="button"
              className="cl-who__wave"
              aria-label="Où cette voix parle dans la séance : un clic prend la réplique la plus proche"
              disabled={!timed.length}
              onClick={(e) => {
                const box = e.currentTarget.getBoundingClientRect();
                const row = nearestLine(
                  timed,
                  ((e.clientX - box.left) / box.width) * duration,
                );
                const next = row ? longest.indexOf(row) : -1;
                if (next >= 0) {
                  setAt(next);
                  hear(row);
                }
              }}
            >
              {wave.map((b, i) => (
                <i
                  key={i}
                  data-mine={b.mine || undefined}
                  style={{ height: `${Math.max(4, b.level * 100)}%` }}
                />
              ))}
              {mark != null && (
                <b
                  className="cl-who__mark"
                  style={{ left: `${mark * 100}%` }}
                />
              )}
            </button>
          )}
        </div>
        <div className="cl-who__pick cl-sheet">
          <PeoplePicker
            query={query}
            onQuery={setQuery}
            listed={whoOrder(speaker, people, voices, attendees)}
            known={people}
            spaceName={spaceName}
            columns={4}
            autoFocus
            isOn={(p) => p.id === picked?.id}
            onTile={(p) => setPicked((was) => (was?.id === p.id ? null : p))}
            note={(p) =>
              p.id === proposed?.id && !speaker.named
                ? "voix reconnue"
                : hasVoice(p, speaker, voices)
                  ? "a déjà une voix"
                  : null
            }
            onAddGuest={addGuest}
            onMakeMember={makeMember}
            onEnter={(only) => {
              // A name typed that leaves one person: that one, not the one chosen before.
              if (only) setPicked(only);
              confirm(only ?? picked);
            }}
          />
        </div>
      </div>
      <div className="cl-who__foot">
        <Button
          label="Passer cette voix"
          variant="secondary"
          onClick={onSkip}
        />
        {error ? (
          <span className="cl-who__error" role="alert">
            {error}
          </span>
        ) : (
          notice && (
            <span className="cl-who__notice" role="status">
              {notice}
            </span>
          )
        )}
        <button
          type="button"
          className="cl-who__ok"
          disabled={!picked || busy}
          onClick={() => confirm()}
        >
          {picked
            ? merges
              ? `Réunir avec la voix de ${picked.name}`
              : `C'est ${picked.name}`
            : "Nommer"}
          <kbd>Entrée</kbd>
        </button>
      </div>
      </div>
    </Dialog>
  );
}
