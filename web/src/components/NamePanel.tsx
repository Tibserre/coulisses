import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, Plus, UserRound } from "lucide-react";
import type { EditRequest, Person, Speaker } from "../api.ts";
import { speakerInk, speakerTint } from "../theme/shared.ts";
import { nameChoices, type NameChoice } from "../transcript.ts";

type View = "who" | "character" | "same";

/** Naming a voice in place (art direction: without leaving the review): the name turns
 *  into a field where it was, and the list floats just under it, held to its line. Typing filters the people
 *  of the space; ↑ ↓ and Enter choose; a name not found becomes a guest, or a free name.
 *  The rare cases (a character played by someone, the same person as another voice) are
 *  a second view of the same list. Escape or a click elsewhere closes it. */
export function NameEditor({
  speaker,
  people,
  voices,
  onCorrect,
  onAddGuest,
  onShowLines,
  onClose,
}: {
  speaker: Speaker;
  people: Person[];
  voices: Speaker[];
  onCorrect: (correction: EditRequest) => Promise<void>;
  onAddGuest: (name: string) => Promise<Person>;
  /** Shows this voice's lines only. */
  onShowLines: (label: string) => void;
  /** Closed; by the keyboard (Escape), the focus goes back to the voice's name. */
  onClose: (byKeyboard: boolean) => void;
}) {
  const label = speaker.label;
  const root = useRef<HTMLSpanElement>(null);
  const field = useRef<HTMLInputElement>(null);
  const [view, setView] = useState<View>("who");
  const [query, setQuery] = useState("");
  const [character, setCharacter] = useState(speaker.character ?? "");
  const [active, setActive] = useState(0);
  /** The arrows were used: Enter takes the line they chose, even with nothing typed. */
  const [moved, setMoved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const busy = useRef(false);

  // A click anywhere else closes it, as Escape does; never while something is being saved
  // (its refusal would have nowhere to be said).
  useEffect(() => {
    const away = (e: PointerEvent) => {
      if (!busy.current && !root.current?.contains(e.target as Node)) onClose(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [onClose]);

  const typedQuery = view === "character" ? "" : query;
  const choices = nameChoices(view, speaker, people, voices, typedQuery);
  // Each view starts empty and typed into; « Joué par » starts on who plays it now, the
  // first view on the person whose voice it seems to be (Enter confirms, ADR 0057).
  useEffect(() => {
    setQuery("");
    field.current?.focus();
    const now =
      view === "character"
        ? choices.findIndex((c) => c.kind === "person" && c.person.id === speaker.person_id)
        : view === "who" && speaker.proposal
          ? 0
          : -1;
    setActive(Math.max(0, now));
    setMoved(now >= 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on each view only
  }, [view]);

  /** Every action reports its refusal here: never an unhandled error (P8). */
  const safely = async (action: () => Promise<unknown>) => {
    if (busy.current) return;
    busy.current = true;
    setWorking(true);
    try {
      await action();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      busy.current = false;
      setWorking(false);
    }
  };
  const assign = (fields: Partial<Extract<EditRequest, { kind: "assign_speaker" }>>) =>
    label === null ? Promise.resolve() : safely(() => onCorrect({ kind: "assign_speaker", speaker: label, ...fields }));

  const run = (c: NameChoice) => {
    if (label === null) return;
    if (c.kind === "voice") return void safely(() => onCorrect({ kind: "merge_speakers", source: label, target: c.voice.label! }));
    if (c.kind === "free") return void assign({ name: c.name });
    if (c.kind === "guest")
      return void safely(async () => {
        const guest = await onAddGuest(c.name);
        await onCorrect({ kind: "assign_speaker", speaker: label, person_id: guest.id });
      });
    if (view === "character") {
      if (!character.trim()) {
        setError("Écrivez d'abord le nom du personnage.");
        field.current?.focus();
        return;
      }
      return void assign({ person_id: c.person.id, character: character.trim() });
    }
    void assign({ person_id: c.person.id });
  };

  const content = (c: NameChoice): ReactNode => {
    if (c.kind === "person") {
      const p = c.person;
      const note =
        view === "character"
          ? p.id === speaker.person_id && speaker.character
            ? "le joue"
            : ""
          : p.id === speaker.person_id && !speaker.character
            ? "actuel"
            : view === "who" && p.id === speaker.proposal?.person_id
              ? "voix reconnue"
              : p.kind === "guest"
              ? "invité"
              : (p.role ?? "");
      return (
        <>
          <span className="cl-avatar cl-avatar--sm" style={{ background: speakerTint(p.color_slot), color: speakerInk(p.color_slot) }} aria-hidden>
            {p.name.trim().charAt(0).toUpperCase()}
          </span>
          <span className="cl-nameedit__label">{p.name}</span>
          <span className="cl-nameedit__note">{note}</span>
        </>
      );
    }
    if (c.kind === "voice")
      return (
        <>
          <span className="cl-dot" style={{ background: inkOf(c.voice) }} aria-hidden />
          <span className="cl-nameedit__label">{c.voice.name}</span>
          <span className="cl-nameedit__note">fusionner</span>
        </>
      );
    const Icon = c.kind === "guest" ? Plus : UserRound;
    return (
      <>
        <Icon size={16} strokeWidth={1.75} className="cl-nameedit__icon" aria-hidden />
        <span className="cl-nameedit__label">{c.kind === "guest" ? `Ajouter « ${c.name} » comme invité` : `« ${c.name} », sans fiche`}</span>
      </>
    );
  };
  const keyOf = (c: NameChoice) =>
    c.kind === "person" ? `p${c.person.id}` : c.kind === "voice" ? `v${c.voice.label}` : c.kind;
  const at = Math.min(active, Math.max(0, choices.length - 1));

  const keys = (e: React.KeyboardEvent<HTMLElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (view === "who") onClose(true);
      else setView("who");
    } else if (e.target === field.current && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      if (choices.length) {
        setActive((at + (e.key === "ArrowDown" ? 1 : choices.length - 1)) % choices.length);
        setMoved(true);
      }
    } else if (e.target === field.current && e.key === "Enter") {
      e.preventDefault();
      // Nothing typed nor chosen: Enter only takes the one line there is.
      if (typedQuery.trim() || moved || view === "character" || choices.length === 1) {
        const c = choices[at];
        if (c) run(c);
      }
    }
  };

  // Where one types: the name itself on the first view; the character, or a search.
  const placeholder =
    view === "who"
      ? speaker.name
      : view === "character"
        ? "Nom du personnage"
        : "Chercher une voix";
  const value = view === "character" ? character : query;

  return (
    <span ref={root} className="cl-nameedit" onKeyDown={keys}>
      {label === null ? (
        <>
          <span className="cl-name" data-unnamed>
            {speaker.name}
          </span>
          <span className="cl-nameedit__panel">
            <span className="cl-nameedit__empty">Cette réplique n'a pas de voix : donnez-la à une voix.</span>
          </span>
        </>
      ) : (
        <>
          <span className="cl-nameedit__field">
            {view !== "who" && (
              <button type="button" className="cl-nameedit__back" aria-label="Retour" onClick={() => setView("who")}>
                <ArrowLeft size={14} strokeWidth={1.75} />
              </button>
            )}
            <input
              ref={field}
              value={value}
              placeholder={placeholder}
              aria-label={view === "who" ? `Qui parle ? (${speaker.name})` : placeholder}
              aria-autocomplete="list"
              aria-controls="cl-nameedit-list"
              aria-activedescendant={choices[at] ? `cl-nameedit-${keyOf(choices[at])}` : undefined}
              aria-busy={working || undefined}
              spellCheck={false}
              onChange={(e) => {
                if (view === "character") setCharacter(e.target.value);
                else setQuery(e.target.value);
                if (view !== "character") {
                  setActive(0);
                  setMoved(false);
                }
                setError(null);
              }}
            />
          </span>
          <span className="cl-nameedit__panel" role="presentation">
            {view === "character" && <span className="cl-nameedit__title">Joué par…</span>}
            {view === "same" && <span className="cl-nameedit__title">C'est la même personne que…</span>}
            <ul id="cl-nameedit-list" role="listbox" className="cl-nameedit__list" aria-label="Choix">
              {choices.map((c, i) => (
                <li
                  key={keyOf(c)}
                  id={`cl-nameedit-${keyOf(c)}`}
                  role="option"
                  aria-selected={i === at}
                  className="cl-nameedit__item"
                  data-recognised={
                    (view === "who" && c.kind === "person" && c.person.id === speaker.proposal?.person_id) || undefined
                  }
                  onPointerEnter={() => setActive(i)}
                  onClick={() => run(c)}
                >
                  {content(c)}
                </li>
              ))}
              {choices.length === 0 && (
                <li className="cl-nameedit__empty">{view === "same" ? "Aucune autre voix." : "Personne dans l'espace."}</li>
              )}
            </ul>
            {error && <span className="cl-nameedit__error">{error}</span>}
            {view === "who" && (
              <span className="cl-nameedit__more">
                <button type="button" onClick={() => onShowLines(label)}>
                  Ses répliques
                </button>
                <button type="button" onClick={() => setView("character")}>
                  Personnage joué…
                </button>
                {voices.some((v) => v.label !== null && v.label !== label) && (
                  <button type="button" onClick={() => setView("same")}>
                    Même voix que…
                  </button>
                )}
                {speaker.named && (
                  <button type="button" onClick={() => void assign({ person_id: null, name: null, character: null })}>
                    Retirer le nom
                  </button>
                )}
              </span>
            )}
          </span>
        </>
      )}
    </span>
  );
}

function inkOf(speaker: Speaker): string {
  return speaker.color_slot != null
    ? speakerInk(speaker.color_slot)
    : "var(--coulisses-speaker-unknown-ink)";
}
