import { useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Check, ChevronLeft, ChevronRight, Pause, Play, User, X } from "lucide-react";
import {
  api,
  ServiceError,
  type EditRequest,
  type Person,
  type Speaker,
  type Turn,
} from "../api.ts";
import { formatDuration, plural } from "../format.ts";
import {
  askFor,
  hasVoice,
  namingLines,
  nearestLine,
  speechWave,
  waveHeight,
  whoOrder,
  type TurnRow,
} from "../transcript.ts";
import type { Playback } from "../usePlayback.ts";
import { Face, PeoplePicker } from "./AttendeesSheet.tsx";
import { VoiceFace, VoicesMenu } from "./VoicesMenu.tsx";

/** Bars of the session's wave. */
const BARS = 72;
/** A character's disc (ADR 0091): a rounded square with its initial, over the face of who
 *  plays it once chosen (« le double »). */
export function RoleFace({ role, person }: { role: string; person?: Person }) {
  return (
    <span className="cl-double">
      {person && <Face person={person} size="lg" />}
      <span className="cl-face" data-size="lg" data-role aria-hidden>
        {role.trim().charAt(0).toLocaleUpperCase("fr")}
      </span>
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
  sessionId,
  duration,
  pb,
  audioGone,
  dev,
  theatre,
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
  sessionId: string;
  /** The session's length; 0 when unknown (then no wave). */
  duration: number;
  pb: Playback;
  audioGone: boolean;
  dev: boolean;
  /** « Jeu et personnages » (ADR 0091): a name may be a character, played by someone. */
  theatre: boolean;
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
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<Person | null>(null);
  /** A character being cast (ADR 0091): « Qui joue Hamlet ? », then who plays it. */
  const [role, setRole] = useState<string | null>(null);
  /** Someone being added (the « + »), or null for the list. */
  const [adding, setAdding] = useState<string | null>(null);
  /** A yes or no first: the recognised voice (« C'est Marie ? »), or someone who already has
   *  a voice (« C'est aussi Marie ? », the two voices merged on yes). */
  const [asking, setAsking] = useState(() => askFor(speaker, people, voices));
  const [at, setAt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  /** The session's wave measured on its sound (ADR 0092), once ready; meanwhile, or when
   *  there is none (404), the one drawn from the lines' times. */
  const [measured, setMeasured] = useState<number[] | null>(null);
  const [waveNote, setWaveNote] = useState<string | null>(null);
  useEffect(() => {
    let gone = false;
    let timer = 0;
    const ask = () =>
      api.wave(sessionId, BARS).then(
        (w) => {
          // A short session has fewer bars (never more than its 50 ms slices).
          if (!gone && w.levels_db.length > 0) setMeasured(w.levels_db);
        },
        (e: unknown) => {
          if (gone) return;
          // Being measured: asked again a little later.
          if (e instanceof ServiceError && e.status === 409)
            timer = window.setTimeout(() => void ask(), 3000);
          // None (404, said by the service) or another failure: the wave drawn from the
          // lines stays, and why is kept for developer mode.
          else setWaveNote((e as Error).message);
        },
      );
    void ask();
    return () => {
      gone = true;
      window.clearTimeout(timer);
    };
  }, [sessionId]);
  // Each voice starts afresh: its recognised person chosen, its longest line shown.
  useEffect(() => {
    setQuery("");
    setPicked(null);
    setRole(null);
    setAdding(null);
    setAt(0);
    setError(null);
    // The cursor in the search (or on « oui »), once the dialog has put it on its title.
    const t = window.setTimeout(
      () => body.current?.querySelector<HTMLElement>("input, .cl-who__yes")?.focus(),
      0,
    );
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per voice
  }, [label]);
  // A new proposal (another person, after a « non » or its undoing) asks again.
  useEffect(() => {
    setAsking(askFor(speaker, people, voices));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on the proposal only
  }, [label, speaker.proposal?.person_id]);
  // The keyboard follows the right side: on « oui » while asking, else in the search.
  useEffect(() => {
    const t = window.setTimeout(
      () =>
        body.current
          ?.querySelector<HTMLElement>(asking ? ".cl-who__yes" : ".cl-who__pick input")
          ?.focus(),
      0,
    );
    return () => window.clearTimeout(t);
  }, [asking]);

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
  const confirm = (who: Person | null = picked) =>
    who &&
    void run(() =>
      onCorrect({
        kind: "assign_speaker",
        speaker: label,
        person_id: who.id,
        // A character stays a voice apart, played by that person.
        ...(role ? { character: role } : {}),
      }),
    );
  /** No: to the recognised voice, « Ce n'est pas … » (ADR 0057, a correction like another,
   *  undone from the corrections); to a merge, back to the list, the refusal kept too when
   *  the voice had been recognised as that person. */
  const no = () => {
    if (!asking) return;
    // A merge picked from the list: just back to it. One the voice was recognised as: the
    // « no » is kept too (ADR 0057), so the same question does not come back.
    if (asking.merge && speaker.proposal?.person_id !== asking.person.id) {
      setAsking(null);
      return;
    }
    const person = asking.person;
    void run(async () => {
      await onCorrect({ kind: "reject_voice_match", speaker: label, person_id: person.id });
      setAsking(null);
    });
  };
  /** A tile: someone with a voice asks first; anyone else is chosen (or no longer). */
  const pick = (p: Person) => {
    if (!role && hasVoice(p, speaker, voices)) setAsking({ person: p, merge: true });
    else setPicked((was) => (was?.id === p.id ? null : p));
  };
  /** The « + »: a guest added is the voice's name at once; a character asks who plays it. */
  const add = (name: string, character: boolean) => {
    if (character) {
      setRole(name);
      setPicked(null);
      setQuery("");
      setAdding(null);
      return;
    }
    void run(async () => {
      const guest = await onAddGuest(name);
      setQuery("");
      setAdding(null);
      setPicked(guest);
      await onCorrect({
        kind: "assign_speaker",
        speaker: label,
        person_id: guest.id,
        ...(role ? { character: role } : {}),
      });
    });
  };
  const makeMember = (p: Person) =>
    void run(async () => {
      await api.updatePerson(p.id, { kind: "member" });
      await onPeopleChanged();
    });

  const named = voices.filter((v) => v.named && v.label !== null);
  const place = toName.indexOf(speaker);
  const number =
    (place < 0 ? 0 : place) + named.length + (speaker.named ? 0 : 1);
  const timed = lines.filter((r) => r.turn.start != null);
  const wave =
    duration > 0 ? speechWave(turns, label, duration, measured?.length ?? BARS) : [];
  // The measured levels, once there (ADR 0092): the wave's height; the lines' times only
  // say where this voice speaks.
  const heights = measured
    ? measured.map((db) => waveHeight(db))
    : wave.map((b) => b.level);
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
      confirm(asking?.person ?? picked);
    }
  };

  return (
    <Dialog
      isOpen
      onOpenChange={(open) => !open && onClose()}
      width={920}
      maxHeight="90dvh"
      aria-label="Qui parle ?"
    >
      <div ref={body} onKeyDown={onKeyDown} className="cl-who__frame">
      <DialogHeader
        title={
          <span className="cl-who__title">
            Qui parle ?
          <VoicesMenu
            voices={voices}
            toName={toName}
            people={people}
            current={speaker}
            onPick={(v) => v.label && onGo(v.label)}
          />
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
                role ? (
                  <RoleFace role={role} person={chosen} />
                ) : (
                  <Face person={chosen} size="lg" />
                )
              ) : role ? (
                <RoleFace role={role} />
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
          {dev && !measured && waveNote && (
            <p className="cl-who__said">
              Onde dessinée d'après les répliques : {waveNote}
            </p>
          )}
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
                  style={{ height: `${Math.max(4, (heights[i] ?? 0) * 100)}%` }}
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
        {asking ? (
          <div
            className="cl-who__pick cl-who__ask"
            role="group"
            aria-labelledby="cl-who-question"
          >
            <span className="cl-who__askfaces">
              {asking.merge && (
                <span className="cl-who__empty" aria-hidden>
                  <User size={26} strokeWidth={1.5} />
                </span>
              )}
              <Face person={asking.person} size="xl" />
            </span>
            <p id="cl-who-question" className="cl-who__question" aria-live="polite">
              {asking.merge ? `C'est aussi ${asking.person.name} ?` : `C'est ${asking.person.name} ?`}
            </p>
            <span className="cl-who__yesno">
              <button
                type="button"
                className="cl-who__no"
                aria-label={asking.merge ? "Non, revenir à la liste" : `Non, ce n'est pas ${asking.person.name}`}
                title={asking.merge ? "Non, revenir à la liste" : `Non, ce n'est pas ${asking.person.name}`}
                disabled={busy}
                onClick={no}
              >
                <X size={22} strokeWidth={2} />
              </button>
              <button
                type="button"
                className="cl-who__yes"
                aria-label={asking.merge ? "Oui, réunir les deux voix (Entrée)" : "Oui (Entrée)"}
                title={asking.merge ? "Oui, réunir les deux voix (Entrée)" : "Oui (Entrée)"}
                disabled={busy}
                onClick={() => confirm(asking.person)}
              >
                <Check size={30} strokeWidth={2.5} />
              </button>
            </span>
          </div>
        ) : (
          <div className="cl-who__pick cl-sheet">
            {role && (
              <p className="cl-who__cast" aria-live="polite">
                <button
                  type="button"
                  className="cl-who__step"
                  aria-label="Revenir : ce n'est pas un personnage"
                  title="Revenir"
                  onClick={() => {
                    setRole(null);
                    setPicked(null);
                  }}
                >
                  <ChevronLeft size={16} strokeWidth={1.75} />
                </button>
                Qui joue {role} ?
              </p>
            )}
            <PeoplePicker
              query={query}
              onQuery={setQuery}
              listed={whoOrder(speaker, people, voices, attendees)}
              known={people}
              spaceName={spaceName}
              columns={4}
              autoFocus
              isOn={(p) => p.id === picked?.id}
              onTile={pick}
              badge={(p) =>
                !role && hasVoice(p, speaker, voices)
                  ? { tip: `${p.name} a déjà une voix dans cette séance`, wave: true }
                  : null
              }
              adding={adding}
              onAdding={setAdding}
              onAdd={add}
              theatre={theatre && !role}
              busy={busy}
              onMakeMember={makeMember}
              onEnter={(only) => {
                // A name typed that leaves one person: that one, not the one chosen before.
                if (only && !role && hasVoice(only, speaker, voices)) setAsking({ person: only, merge: true });
                else if (only) {
                  setPicked(only);
                  confirm(only);
                } else confirm();
              }}
            />
          </div>
        )}
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
        {/* While asking, the answer is the two discs: no button jumps under the pointer. */}
        {!asking && adding === null && (
          <button
            type="button"
            className="cl-who__ok"
            disabled={!picked || busy}
            onClick={() => confirm()}
          >
            {picked ? (role ? `Joué par ${picked.name}` : `C'est ${picked.name}`) : "Nommer"}
            <kbd>Entrée</kbd>
          </button>
        )}
      </div>
      </div>
    </Dialog>
  );
}
