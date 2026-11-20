import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Tooltip } from "@astryxdesign/core/Tooltip";
import { AudioLines, Check, Minus, Plus, Search, User, X } from "lucide-react";
import { api, type Person, type Session } from "../api.ts";
import { plural } from "../format.ts";
import { attendeesOf, fewerAttendees, toggleAttendee } from "../processing.ts";
import { speakerInk, speakerTint } from "../theme/shared.ts";

/** Who is there while recording (spec §7.1, §7.2): a number, a minimum of voices (P3), and
 *  the names, if one wants. Each change is saved at once, one after the other; what is shown
 *  goes back to the session's once none waits (a refusal puts it back, and is said). */
export function useAttendees(
  session: Session | null,
  onChanged: (session: Session) => void,
  onError: (message: string) => void,
) {
  const fromSession = () => ({
    ids: session?.attendee_ids ?? [],
    count: (session?.attendee_ids.length ?? 0) + (session?.unnamed_attendees ?? 0),
  });
  const [shown, setShown] = useState(fromSession);
  // What was last asked, read by each click: two quick clicks add two.
  const latest = useRef(shown);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const waiting = useRef(0);
  const [settled, setSettled] = useState(0);
  useEffect(() => {
    if (waiting.current > 0) return;
    latest.current = fromSession();
    setShown(latest.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the ids, by value
  }, [session?.attendee_ids.join(), session?.unnamed_attendees, session?.id, settled]);

  const change = (
    make: (was: { ids: number[]; count: number }) => {
      ids: number[];
      count: number;
    },
  ) => {
    if (!session) return;
    const asked = make(latest.current);
    const next = attendeesOf(Math.max(0, asked.count), asked.ids);
    latest.current = { ids: next.ids, count: next.count };
    setShown(latest.current);
    waiting.current += 1;
    queue.current = queue.current
      .then(async () => {
        onChanged(await api.setAttendees(session.id, next.ids, next.unnamed));
      })
      .catch((e: Error) => onError(e.message))
      .finally(() => {
        waiting.current -= 1;
        if (waiting.current === 0) setSettled((n) => n + 1);
      });
  };
  if (!session) return null;
  return {
    ids: shown.ids,
    count: shown.count,
    more: () => change((was) => ({ ...was, count: was.count + 1 })),
    fewer: () => change(fewerAttendees),
    toggle: (id: number) => change((was) => toggleAttendee(was, id)),
    /** Taken back (a guest added by mistake): unchecked, and one fewer if adding them had
     *  raised the number; a « + » made since stays. */
    takeBack: (id: number, raised: boolean) =>
      change((was) => ({
        ids: was.ids.filter((x) => x !== id),
        count: raised ? was.count - 1 : was.count,
      })),
    /** Whether checking one more raises the number: every place has a name. */
    full: () => latest.current.count <= latest.current.ids.length,
  };
}

export type Attendees = NonNullable<ReturnType<typeof useAttendees>>;

const initial = (name: string) => name.trim().charAt(0).toLocaleUpperCase("fr");
const bare = (s: string) =>
  s.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("fr").trim();

/** A person's disc: their initial in their colour (a guest's outlined), or an empty place. */
export function Face({ person, size = "md" }: { person?: Person; size?: "sm" | "md" | "lg" | "xl" }) {
  return person ? (
    <span
      className="cl-face"
      data-size={size}
      data-guest={person.kind === "guest" || undefined}
      style={{
        background: person.kind === "guest" ? undefined : speakerTint(person.color_slot),
        color: speakerInk(person.color_slot),
      }}
      aria-hidden
    >
      {initial(person.name)}
    </span>
  ) : (
    <span className="cl-face" data-size={size} data-empty aria-hidden>
      <User size={size === "lg" ? 16 : 12} strokeWidth={2} />
    </span>
  );
}

/** The places, named first then empty, `max` at most (« +k » for the rest). */
export function Faces({
  attendees,
  people,
  max,
  size,
}: {
  attendees: Pick<Attendees, "ids" | "count">;
  people: Person[];
  max: number;
  size?: "sm" | "md" | "lg";
}) {
  const named = attendees.ids
    .map((id) => people.find((p) => p.id === id))
    .filter((p): p is Person => Boolean(p));
  const places: (Person | undefined)[] = [
    ...named,
    ...Array.from({ length: Math.max(0, attendees.count - named.length) }, () => undefined),
  ];
  const over = places.length > max ? places.length - (max - 1) : 0;
  const shown = over ? places.slice(0, max - 1) : places;
  return (
    <span className="cl-faces">
      {/* No one yet: one place to say who is there, never an empty spot. */}
      {places.length === 0 && (
        <span className="cl-face" data-size={size} data-empty aria-hidden>
          <Plus size={12} strokeWidth={2} />
        </span>
      )}
      {shown.map((p, k) => (
        <Face key={p ? p.id : `vide${k}`} person={p} size={size} />
      ))}
      {over > 0 && (
        <span className="cl-face" data-size={size} data-over aria-hidden>
          +{over}
        </span>
      )}
    </span>
  );
}

/** « Qui est là ? » (D5a): the number with − and +, the places, then the people of the
 *  space to touch, a search that adds a guest, and a guest made a member. */
export function AttendeesSheet({
  isOpen,
  onClose,
  session,
  spaceName,
  people,
  known = people,
  attendees,
  onPeopleChanged,
  onError,
}: {
  isOpen: boolean;
  onClose: () => void;
  session: Session;
  spaceName: string;
  people: Person[];
  /** Everyone of the space, archived ones too: a name typed is never added twice. */
  known?: Person[];
  attendees: Attendees;
  /** A guest added or made a member: the people read again. */
  onPeopleChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  /** The order at opening, those checked first: nothing moves under the pointer. */
  const [order, setOrder] = useState<number[]>([]);
  const [said, setSaid] = useState<{ text: string; undo: () => Promise<void> } | null>(null);
  useEffect(() => {
    if (!isOpen) return;
    setQuery("");
    setAdding(null);
    setSaid(null);
    const checked = new Set(attendees.ids);
    setOrder([
      ...people.filter((p) => checked.has(p.id)).map((p) => p.id),
      ...people.filter((p) => !checked.has(p.id)).map((p) => p.id),
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per opening
  }, [isOpen]);

  const byId = new Map(people.map((p) => [p.id, p]));
  const listed = [
    ...order.map((id) => byId.get(id)).filter((p): p is Person => Boolean(p)),
    ...people.filter((p) => !order.includes(p.id)),
  ];

  const [busy, setBusy] = useState(false);
  const run = async (step: () => Promise<void>) => {
    setBusy(true);
    try {
      await step();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const addGuest = (name: string) =>
    run(async () => {
      const raised = attendees.full();
      const guest = await api.addPerson(session.space_id, { name, kind: "guest" });
      await onPeopleChanged();
      setOrder((o) => [...o.slice(0, attendees.ids.length), guest.id, ...o.slice(attendees.ids.length)]);
      attendees.toggle(guest.id);
      setQuery("");
      setAdding(null);
      setSaid({
        text: `${guest.name} participe en invité.`,
        // Taken back: unchecked and archived, never deleted (P8).
        undo: async () => {
          attendees.takeBack(guest.id, raised);
          await api.updatePerson(guest.id, { archived: true });
          await onPeopleChanged();
        },
      });
    });
  const makeMember = (p: Person) =>
    run(async () => {
      await api.updatePerson(p.id, { kind: "member" });
      await onPeopleChanged();
      setSaid({
        text: `${p.name} est membre de ${spaceName}.`,
        undo: async () => {
          await api.updatePerson(p.id, { kind: "guest" });
          await onPeopleChanged();
        },
      });
    });

  const close = () => onClose();
  return (
    <Dialog isOpen={isOpen} onOpenChange={(open) => !open && close()} width={580}>
      <DialogHeader title="Qui est là ?" onOpenChange={close} />
      <div className="cl-sheet">
        <div className="cl-sheet__count">
          <Counter attendees={attendees} size="md" />
          <Faces attendees={attendees} people={people} max={12} size="md" />
        </div>
        <hr className="cl-sheet__rule" />
        <div className="cl-sheet__say">
          <span className="cl-sheet__title">Dire qui est là</span>
          <span className="cl-sheet__opt">facultatif</span>
        </div>
        <p className="cl-sheet__why">Les voix seront plus faciles à reconnaître ensuite.</p>
        <PeoplePicker
          query={query}
          onQuery={setQuery}
          listed={listed}
          spaceName={spaceName}
          isOn={(p) => attendees.ids.includes(p.id)}
          onTile={(p) => attendees.toggle(p.id)}
          adding={adding}
          onAdding={setAdding}
          onAdd={(name) => void (!busy && addGuest(name))}
          known={known}
          busy={busy}
          onMakeMember={(p) => void makeMember(p)}
        />
        <div className="cl-sheet__foot">
          {said ? (
            <span role="status">
              {said.text}{" "}
              <button
                type="button"
                className="cl-linkbtn"
                onClick={() => {
                  const undo = said.undo;
                  setSaid(null);
                  void run(undo);
                }}
              >
                Annuler
              </button>
            </span>
          ) : (
            <span className="cl-sheet__opt">
              {attendees.ids.length === 0
                ? "Personne de nommé"
                : `${plural(attendees.ids.length, "nommée", "nommées")} sur ${attendees.count}`}
            </span>
          )}
          <Button label="Terminé" variant="primary" onClick={close} />
        </div>
      </div>
    </Dialog>
  );
}

/** − N + « présents ». */
export function Counter({ attendees, size }: { attendees: Attendees; size: "md" | "lg" }) {
  return (
    <div className="cl-counter" data-size={size} role="group" aria-label="Nombre de présents">
      <div className="cl-counter__row">
        <button
          type="button"
          className="cl-counter__step"
          aria-label="Une personne de moins"
          disabled={attendees.count === 0}
          onClick={(e) => {
            e.currentTarget.blur();
            attendees.fewer();
          }}
        >
          <Minus size={16} strokeWidth={1.75} aria-hidden />
        </button>
        <span className="cl-counter__num" aria-live="polite">
          {attendees.count}
        </span>
        <button
          type="button"
          className="cl-counter__step"
          aria-label="Une personne de plus"
          onClick={(e) => {
            e.currentTarget.blur();
            attendees.more();
          }}
        >
          <Plus size={16} strokeWidth={1.75} aria-hidden />
        </button>
      </div>
      <span className="cl-counter__cap">{attendees.count === 1 ? "présent" : "présents"}</span>
    </div>
  );
}

/** What a tile says on hover: its whole name when cut, then what its mark says. */
export function tileTip(cutName: string | null, mark: string | null): string {
  return [cutName, mark].filter(Boolean).join(" · ");
}

/** The people of the space to pick from (« Qui est là ? », « Qui parle ? »): the search, the
 *  big discs (two lines of name at most), a guest outlined with « + » to make them a member.
 *  The first disc is « + »: it opens the adding of someone, in place of the list. */
export function PeoplePicker({
  query,
  onQuery,
  listed,
  known = listed,
  spaceName,
  isOn,
  onTile,
  badge,
  columns = 6,
  autoFocus = false,
  adding,
  onAdding,
  onAdd,
  theatre = false,
  busy = false,
  onMakeMember,
  onEnter,
}: {
  query: string;
  onQuery: (query: string) => void;
  /** In the order shown. */
  listed: Person[];
  /** Everyone a typed name is matched against, archived included (no one in double);
   *  by default those listed. */
  known?: Person[];
  spaceName: string;
  isOn: (p: Person) => boolean;
  onTile: (p: Person) => void;
  /** A small wave on the disc, said on hover (« Marie a déjà une voix dans cette séance »):
   *  no small text under the name. */
  badge?: (p: Person) => { tip: string; wave: boolean } | null;
  columns?: 4 | 6;
  autoFocus?: boolean;
  /** The name being added, or null for the list. */
  adding: string | null;
  onAdding: (name: string | null) => void;
  /** A new guest (invité d'office), or with « Jeu et personnages » a character (ADR 0091). */
  onAdd: (name: string, character: boolean) => void;
  /** « Une personne | Un personnage » under the name. */
  theatre?: boolean;
  busy?: boolean;
  onMakeMember: (p: Person) => void;
  /** Entrée on the search: with the one person a name typed leaves, if it does. */
  onEnter?: (only: Person | null) => void;
}) {
  const q = bare(query);
  const found = q ? listed.filter((p) => bare(p.name).includes(q)) : listed;
  const only = q
    ? (found.find((p) => bare(p.name) === q) ?? (found.length === 1 ? found[0] : null))
    : null;
  // Back from adding someone: the keyboard back in the search.
  const back = useRef(false);
  if (adding !== null) back.current = true;
  if (adding !== null)
    return (
      <AddPerson
        name={adding}
        onName={onAdding}
        known={known}
        spaceName={spaceName}
        theatre={theatre}
        busy={busy}
        onCancel={() => onAdding(null)}
        onAdd={onAdd}
        onPick={(p) => {
          if (!isOn(p)) onTile(p);
          onAdding(null);
        }}
      />
    );
  return (
    <>
      <label className="cl-sheet__find" data-typed={query ? true : undefined}>
        <Search size={14} strokeWidth={1.75} aria-hidden />
        <input
          type="text"
          value={query}
          autoFocus={autoFocus || back.current}
          placeholder="Chercher ou ajouter un nom"
          aria-label="Chercher ou ajouter un nom"
          onChange={(e) => onQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            e.preventDefault();
            // A name that leaves no one: its adding, the name already filled in.
            if (q && !only) onAdding(query.trim());
            else onEnter?.(only);
          }}
        />
        {query && (
          <button type="button" className="cl-sheet__clear" aria-label="Effacer" onClick={() => onQuery("")}>
            <X size={14} strokeWidth={1.75} />
          </button>
        )}
      </label>
      <div className="cl-sheet__scroll">
        <ul className="cl-sheet__grid" data-columns={columns} aria-label="Personnes de l'espace">
          <li className="cl-sheet__cell">
            <button
              type="button"
              className="cl-sheet__tile cl-sheet__add"
              aria-label={q ? `Ajouter « ${query.trim()} »` : "Ajouter quelqu'un"}
              onClick={() => onAdding(query.trim())}
            >
              <span className="cl-face" data-size="lg" data-empty aria-hidden>
                <Plus size={18} strokeWidth={1.75} />
              </span>
              <span className="cl-sheet__name">{query.trim() || "Ajouter"}</span>
            </button>
          </li>
          {found.map((p) => (
            <li key={p.id} className="cl-sheet__cell">
              <Tile person={p} on={isOn(p)} badge={badge?.(p) ?? null} onToggle={() => onTile(p)} />
              {p.kind === "guest" && (
                <Tooltip
                  content={
                    <>
                      Passer membre
                      <small className="cl-sheet__tipnote">{p.name} participe en invité</small>
                    </>
                  }
                >
                  <button
                    type="button"
                    className="cl-sheet__member"
                    aria-label={`Passer ${p.name} membre de ${spaceName}`}
                    onClick={() => onMakeMember(p)}
                  >
                    <Plus size={12} strokeWidth={2.25} aria-hidden />
                  </button>
                </Tooltip>
              )}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

/** Adding someone, drawn like « C'est Marie ? »: the big disc (« + » until a name, then its
 *  initial, outlined: a guest), the name across the column, then no and yes (Entrée). */
function AddPerson({
  name,
  onName,
  known,
  spaceName,
  theatre,
  busy,
  onCancel,
  onAdd,
  onPick,
}: {
  name: string;
  onName: (name: string) => void;
  known: Person[];
  spaceName: string;
  theatre: boolean;
  busy: boolean;
  onCancel: () => void;
  onAdd: (name: string, character: boolean) => void;
  /** The name typed is someone's already: that person, rather than a second one. */
  onPick: (p: Person) => void;
}) {
  const [character, setCharacter] = useState(false);
  const typed = name.trim();
  // Someone of the space already bears it (archived ones too): no one in double.
  const taken = character ? null : (known.find((p) => bare(p.name) === bare(typed)) ?? null);
  const can = typed !== "" && !busy && !taken?.archived;
  const add = () => {
    if (!can) return;
    if (taken) onPick(taken);
    else onAdd(typed, character);
  };
  const yes = taken
    ? taken.archived
      ? `${taken.name} est archivé dans ${spaceName}`
      : `Choisir ${taken.name}, déjà dans ${spaceName} (Entrée)`
    : character
      ? `Ajouter le personnage (Entrée)`
      : `Ajouter (Entrée)`;
  return (
    <div className="cl-who__ask cl-add" role="group" aria-label="Ajouter quelqu'un">
      {typed === "" ? (
        <span className="cl-face" data-size="xl" data-empty aria-hidden>
          <Plus size={28} strokeWidth={1.5} />
        </span>
      ) : character ? (
        <span className="cl-face" data-size="xl" data-role data-character aria-hidden>
          {initial(typed)}
        </span>
      ) : (
        <Face
          person={taken ?? { id: 0, space_id: 0, kind: "guest", name: typed, role: null, color_slot: 0, archived: false }}
          size="xl"
        />
      )}
      <input
        className="cl-add__name"
        type="text"
        value={name}
        autoFocus
        placeholder={character ? "Son nom de personnage" : "Son nom"}
        aria-label={character ? "Nom du personnage" : "Son nom"}
        onChange={(e) => onName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter") return;
          e.preventDefault();
          e.stopPropagation();
          add();
        }}
      />
      {theatre && (
        <SegmentedControl
          label="Une personne ou un personnage"
          value={character ? "role" : "person"}
          onChange={(v: string) => setCharacter(v === "role")}
          size="sm"
        >
          <SegmentedControlItem value="person" label="Une personne" />
          <SegmentedControlItem value="role" label="Un personnage" />
        </SegmentedControl>
      )}
      {taken && (
        <span className="cl-sr" role="status">
          {yes}
        </span>
      )}
      <span className="cl-who__yesno">
        <button type="button" className="cl-who__no" aria-label="Annuler" title="Annuler" onClick={onCancel}>
          <X size={18} strokeWidth={2} />
        </button>
        <button
          type="button"
          className="cl-who__yes"
          aria-label={yes}
          title={yes}
          disabled={!can}
          onClick={add}
        >
          <Check size={20} strokeWidth={2.25} />
        </button>
      </span>
    </div>
  );
}

/** A person in the sheet's grid: the name holds two lines, then « … »; cut, the whole name comes on hover. */
function Tile({
  person,
  on,
  badge,
  onToggle,
}: {
  person: Person;
  on: boolean;
  badge: { tip: string; wave: boolean } | null;
  onToggle: () => void;
}) {
  const name = useRef<HTMLSpanElement>(null);
  const [cut, setCut] = useState(false);
  useLayoutEffect(() => {
    const el = name.current;
    if (el) setCut(el.scrollHeight > el.clientHeight + 1);
  }, [person.name]);
  const tile = (
      <button
        type="button"
        className="cl-sheet__tile"
        aria-pressed={on}
        data-on={on || undefined}
        onClick={onToggle}
      >
        <span className="cl-sheet__disc">
          <Face person={person} size="lg" />
          {on && (
            <span className="cl-sheet__ok" aria-hidden>
              <Check size={11} strokeWidth={3} />
            </span>
          )}
          {badge?.wave && (
            <span className="cl-sheet__badge" aria-hidden>
              <AudioLines size={11} strokeWidth={2} />
            </span>
          )}
        </span>
        <span ref={name} className="cl-sheet__name">
          {person.name}
        </span>
      </button>
  );
  // Only a cut name or a wave gets a tooltip: otherwise screen readers would hear the name twice.
  // The whole name when cut, and what the wave says.
  const tip = tileTip(cut ? person.name : null, badge?.tip ?? null);
  return tip ? <Tooltip content={tip}>{tile}</Tooltip> : tile;
}
