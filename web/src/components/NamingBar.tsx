import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  SkipForward,
  X,
} from "lucide-react";
import type { EditRequest, Person, Speaker } from "../api.ts";
import { speakerInk } from "../theme/shared.ts";
import { choiceNote, namingChoices, type NameChoice } from "../transcript.ts";

/** How many names are offered under the field at once. */
const SHOWN = 5;

/** The guided naming of the voices (ADR 0062): a thin bar floating over the transcript,
 *  under the line being looked at, which nothing pushes. ‹ › go from one of the voice's
 *  lines to another, ▶ hears it; the field offers who it may be (the recognised person,
 *  then those present without a voice); ✓ names it and goes to the next voice. Every
 *  refusal is said under it (P8). */
export function NamingBar({
  speaker,
  position,
  remaining,
  line,
  lines,
  hearing,
  cannotHear = null,
  dev = false,
  people,
  voices,
  attendees,
  onPrevious,
  onNext,
  onHear,
  onSkip,
  onClose,
  onCorrect,
  onAddGuest,
}: {
  speaker: Speaker;
  /** This voice among those left to name (from 1), and how many are left. */
  position: number;
  remaining: number;
  /** The line looked at among the voice's lines (from 1), and how many it has. */
  line: number;
  lines: number;
  hearing: boolean;
  /** Why this line cannot be heard (the audio deleted, no measured start), if so. */
  cannotHear?: string | null;
  /** Developer mode: the distance of a recognised voice (ADR 0057). */
  dev?: boolean;
  people: Person[];
  voices: Speaker[];
  attendees: readonly number[];
  onPrevious: () => void;
  onNext: () => void;
  onHear: () => void;
  onSkip: () => void;
  onClose: () => void;
  onCorrect: (correction: EditRequest) => Promise<void>;
  onAddGuest: (name: string) => Promise<Person>;
}) {
  const field = useRef<HTMLInputElement>(null);
  const [typed, setTyped] = useState("");
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const label = speaker.label;
  /** A click on a button of the bar leaves the cursor in the field (keys go on working). */
  const keep = (e: React.MouseEvent) => e.preventDefault();

  // Each voice starts with an empty field, the cursor in it.
  useEffect(() => {
    setTyped("");
    setActive(0);
    setError(null);
    field.current?.focus();
  }, [label]);

  const choices = namingChoices(
    speaker,
    people,
    voices,
    attendees,
    typed,
  ).slice(0, SHOWN);

  const give = async (c: NameChoice | undefined) => {
    if (!c || label === null || busy.current) return;
    busy.current = true;
    try {
      if (c.kind === "voice")
        await onCorrect({
          kind: "merge_speakers",
          source: label,
          target: c.voice.label!,
        });
      else if (c.kind === "free")
        await onCorrect({
          kind: "assign_speaker",
          speaker: label,
          name: c.name,
        });
      else if (c.kind === "guest") {
        const guest = await onAddGuest(c.name);
        await onCorrect({
          kind: "assign_speaker",
          speaker: label,
          person_id: guest.id,
        });
      } else
        await onCorrect({
          kind: "assign_speaker",
          speaker: label,
          person_id: c.person.id,
        });
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      busy.current = false;
    }
  };

  /** « Ce n'est pas elle / lui » (ADR 0057): a correction like another, undone from the
   *  corrections (or Cmd-Z, outside the field). */
  const reject = async () => {
    if (label === null || !speaker.proposal) return;
    try {
      await onCorrect({
        kind: "reject_voice_match",
        speaker: label,
        person_id: speaker.proposal.person_id,
      });
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div
      className="cl-namingbar"
      role="dialog"
      aria-label={`Nommer ${speaker.name}`}
    >
      <div className="cl-namingbar__row">
        <span className="cl-namingbar__who">
          <span className="cl-name" data-unnamed>
            {speaker.name}
          </span>
          <span className="cl-namingbar__count">
            {position}/{remaining}
          </span>
        </span>
        <span className="cl-namingbar__sep" aria-hidden />
        <button
          type="button"
          className="cl-iconbtn"
          onMouseDown={keep}
          onClick={onPrevious}
          aria-label="Réplique précédente de cette voix (←)"
          title="Réplique précédente de cette voix (←)"
        >
          <ChevronLeft size={17} strokeWidth={1.75} />
        </button>
        <span className="cl-namingbar__count">
          {line} / {lines}
        </span>
        <button
          type="button"
          className="cl-iconbtn"
          onMouseDown={keep}
          onClick={onNext}
          aria-label="Réplique suivante de cette voix (→)"
          title="Réplique suivante de cette voix (→)"
        >
          <ChevronRight size={17} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          className="cl-iconbtn"
          onMouseDown={keep}
          onClick={onHear}
          disabled={!!cannotHear}
          aria-label={
            hearing ? "Arrêter l'écoute" : "Écouter cette réplique (Espace)"
          }
          title={
            hearing ? "Arrêter l'écoute" : "Écouter cette réplique (Espace)"
          }
        >
          {hearing ? (
            <Pause size={16} strokeWidth={1.75} />
          ) : (
            <Play size={16} strokeWidth={1.75} />
          )}
        </button>
        <span className="cl-namingbar__sep" aria-hidden />
        <input
          ref={field}
          className="cl-namingbar__field"
          placeholder="Qui est-ce ?"
          value={typed}
          autoComplete="off"
          spellCheck={false}
          aria-label="Nom de cette voix"
          onChange={(e) => {
            setTyped(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void give(choices[active]);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(choices.length - 1, a + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(0, a - 1));
            } else if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            } else if (!typed && e.key === "ArrowLeft") {
              e.preventDefault();
              onPrevious();
            } else if (!typed && e.key === "ArrowRight") {
              e.preventDefault();
              onNext();
            } else if (!typed && e.key === " ") {
              e.preventDefault();
              if (!cannotHear) onHear();
            }
          }}
        />
        <button
          type="button"
          className="cl-iconbtn cl-namingbar__ok"
          onMouseDown={keep}
          onClick={() => void give(choices[active])}
          disabled={!choices.length}
          aria-label="Nommer, puis voix suivante (Entrée)"
          title="Nommer, puis voix suivante (Entrée)"
        >
          <Check size={17} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          className="cl-iconbtn"
          onMouseDown={keep}
          onClick={onSkip}
          aria-label="Passer cette voix"
          title="Passer cette voix"
        >
          <SkipForward size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          className="cl-iconbtn"
          onClick={onClose}
          aria-label="Arrêter de nommer (Échap)"
          title="Arrêter de nommer (Échap)"
        >
          <X size={16} strokeWidth={1.75} />
        </button>
      </div>
      {choices.length > 0 && (
        <ul
          className="cl-namingbar__list"
          role="listbox"
          aria-label="Qui est-ce ?"
        >
          {choices.map((c, i) => {
            const name =
              c.kind === "person"
                ? c.person.name
                : c.kind === "voice"
                  ? c.voice.name
                  : c.name;
            const recognised =
              c.kind === "person" &&
              c.person.id === speaker.proposal?.person_id;
            return (
              <li
                key={`${c.kind}:${name}`}
                role="option"
                aria-selected={i === active}
              >
                <button
                  type="button"
                  className="cl-namingbar__choice"
                  data-active={i === active || undefined}
                  // The focus stays in the field; the choice is made on click (or by
                  // the keyboard, once tabbed to).
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => void give(c)}
                  onPointerEnter={() => setActive(i)}
                >
                  <span
                    style={
                      c.kind === "person"
                        ? { color: speakerInk(c.person.color_slot) }
                        : undefined
                    }
                  >
                    {c.kind === "guest" || c.kind === "free"
                      ? `« ${name} »`
                      : name}
                  </span>
                  <span className="cl-namingbar__note">
                    {choiceNote(c, speaker, attendees, voices)}
                    {dev && recognised && speaker.proposal
                      ? ` · distance ${speaker.proposal.distance.toFixed(3)}`
                      : ""}
                  </span>
                </button>
                {recognised && (
                  <button
                    type="button"
                    className="cl-iconbtn"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => void reject()}
                    aria-label={`Ce n'est pas ${name}`}
                    title={`Ce n'est pas ${name}`}
                  >
                    <X size={13} strokeWidth={1.75} />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {error && (
        <p className="cl-namingbar__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
