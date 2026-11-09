import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import {
  api,
  type ActionInfo,
  type GlossaryEntry,
  type Language,
  type Person,
  type Space,
  type SpaceAction,
  type SpaceTemplate,
} from "../api.ts";
import { ChevronDown, Plus } from "lucide-react";
import { LanguageDownloadDialog, LanguagePick, useLanguages } from "../components/Languages.tsx";
import { labelOf, languageWord } from "../languages.ts";
import { EditableTitle } from "../components/EditableTitle.tsx";
import { plural } from "../format.ts";
import { speakerInk, speakerTint } from "../theme/shared.ts";

/** A space's settings (a troupe, a team, a client; ADR 0020), opened from its « … » menu
 *  in the side column: its name (the page's title, typed into in place), its people, its
 *  glossary, the summary it offers first.
 *  Nothing is deleted here: people and terms are archived, so past sessions keep them. */
export function SpacePage({ id, onChanged }: { id: number; onChanged: () => Promise<void> }) {
  const [spaces, setSpaces] = useState<Space[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSpaces(await api.spaces());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const space = spaces?.find((s) => s.id === id) ?? null;
  return (
    <main className="cl-spacepage">
      {error && <Banner status="error" title="Action refusée" description={error} isDismissable onDismiss={() => setError(null)} />}
      {spaces && !space && <Banner status="error" title="Espace introuvable" />}
      {space && (
        <SpaceDetail
          key={space.id}
          space={space}
          onChanged={async () => {
            await load();
            await onChanged();
          }}
          onError={setError}
        />
      )}
    </main>
  );
}

/** « Nouvel espace » : its name and its starting template (ADR 0020). */
export function NewSpaceForm({ onCreated, onCancel }: { onCreated: (space: Space) => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<SpaceTemplate>("impro");
  const [error, setError] = useState<string | null>(null);
  const create = async () => {
    try {
      onCreated(await api.createSpace(name, template));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="cl-newspace">
      <TextInput
        label="Nom"
        placeholder="Une troupe, une équipe, un client"
        value={name}
        onChange={setName}
        onEnter={() => void create()}
      />
      <label className="cl-select">
        <span>Modèle de départ</span>
        <select value={template} onChange={(e) => setTemplate(e.target.value as SpaceTemplate)}>
          <option value="impro">Troupe d'impro : Résumé Impro proposé</option>
          <option value="reunion">Réunions de travail : compte rendu de réunion proposé</option>
          <option value="vide">Vide : aucun résumé proposé</option>
        </select>
      </label>
      {error && <Banner status="error" title="Refusé" description={error} />}
      <div className="cl-newspace__actions">
        <Button variant="ghost" label="Annuler" onClick={onCancel} />
        <Button variant="primary" label="Créer l'espace" onClick={() => void create()} isDisabled={!name.trim()} />
      </div>
    </div>
  );
}

function SpaceDetail({
  space,
  onChanged,
  onError,
}: {
  space: Space;
  onChanged: () => Promise<void>;
  onError: (message: string | null) => void;
}) {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntry[] | null>(null);

  const load = useCallback(async () => {
    const [p, g] = await Promise.all([api.people(space.id), api.glossary(space.id)]);
    setPeople(p);
    setGlossary(g);
  }, [space.id]);
  useEffect(() => {
    void load().catch((e: Error) => onError(e.message));
  }, [load, onError]);

  /** Done, then everything read again; refused, said at the top of the page. */
  const attempt: Attempt = async (action) => {
    try {
      await action();
      await load();
      await onChanged();
      onError(null);
      return true;
    } catch (e) {
      onError((e as Error).message);
      return false;
    }
  };

  const present = (people ?? []).filter((p) => !p.archived);
  const members = present.filter((p) => p.kind === "member").length;
  const guests = present.length - members;
  const terms = (glossary ?? []).filter((e) => !e.archived).length;

  return (
    <div className="cl-space">
      <header className="cl-space__head">
        <Text type="supporting">Paramètres de l'espace</Text>
        <EditableTitle
          title={space.name}
          onSave={async (name) => {
            await api.updateSpace(space.id, { name });
            await onChanged();
          }}
        />
        <Text color="secondary" className="cl-space__counts">
          {people !== null && glossary !== null && [
            plural(members, "membre", "membres"),
            guests ? plural(guests, "invité", "invités") : null,
            plural(terms, "terme", "termes"),
            space.archived ? "archivé" : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </Text>
      </header>

      <PeopleSection spaceId={space.id} people={people} attempt={attempt} />
      <GlossarySection spaceId={space.id} entries={glossary} attempt={attempt} />
      <AutoSummaries spaceId={space.id} onError={onError} />
      <SpaceLanguage space={space} attempt={attempt} onError={onError} />

      <section className="cl-space__section">
        <Heading level={3}>Voix</Heading>
        <Switch
          label="Reconnaître les voix d'une séance à l'autre"
          description="Activé, Coulisses reconnaît les voix déjà nommées et propose leur nom (« C'est Marie ? ») : c'est toujours vous qui confirmez. Désactivé, les voix ne sont jamais comparées d'une séance à l'autre et on les nomme à chaque séance."
          value={space.voice_recognition}
          onChange={(on) => void attempt(() => api.updateSpace(space.id, { voice_recognition: on }))}
        />
      </section>

      {/* At the end: archiving is rare, and never next to what one types. */}
      <section className="cl-space__section">
        <Heading level={3}>{space.archived ? "Espace archivé" : "Archiver l'espace"}</Heading>
        <Text type="supporting">
          {space.archived
            ? "Il est rangé à part dans la colonne ; ses séances y restent."
            : "Il est rangé à part dans la colonne, avec ses séances, qui restent consultables ; on n'y commence plus de séance. Rien n'est supprimé."}
        </Text>
        <div>
          <Button
            size="sm"
            label={space.archived ? "Désarchiver" : "Archiver l'espace"}
            clickAction={async () => {
              await attempt(() => api.updateSpace(space.id, { archived: !space.archived }));
            }}
          />
        </div>
      </section>
    </div>
  );
}

/** The language its new sessions take (ADR 0072): changing it touches none of the
 *  sessions there already. One not on this Mac is offered to download, never fetched alone. */
function SpaceLanguage({
  space,
  attempt,
  onError,
}: {
  space: Space;
  attempt: Attempt;
  onError: (message: string | null) => void;
}) {
  const { languages, reload } = useLanguages(onError);
  const [toDownload, setToDownload] = useState<Language | null>(null);
  const label = languages ? labelOf(languages, space.language) : null;
  return (
    <section className="cl-space__section">
      <Heading level={3}>Langue des séances</Heading>
      <Text color="secondary">
        Les nouvelles séances de cet espace sont transcrites dans cette langue.
        La changer ne touche pas les séances déjà là ; chacune se change à part.
      </Text>
      {languages === null ? (
        <Skeleton width={160} height={20} radius={1} />
      ) : (
        <div>
          <LanguagePick
            languages={languages}
            value={space.language}
            title="Langue des séances"
            onPick={(l) =>
              void attempt(() =>
                api.updateSpace(space.id, { language: l.language }),
              ).then((done) => {
                if (done && !l.installed) setToDownload(l);
              })
            }
          >
            <button type="button" className="cl-modelpick">
              <span className="cl-modelpick__name">
                {label ?? "Langue plus prise en charge"}
              </span>
              <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
            </button>
          </LanguagePick>
        </div>
      )}
      {languages !== null && label === null && (
        <Banner
          status="warning"
          title="Cette langue n'est plus prise en charge"
          description="Ses nouvelles séances attendront qu'on leur choisisse une autre langue. Choisissez-en une pour l'espace."
        />
      )}
      <LanguageDownloadDialog
        language={toDownload}
        after={
          toDownload
            ? `L'espace passe en ${languageWord(toDownload.label)} dès maintenant. Une séance traitée avant la fin du téléchargement l'attend, sans bloquer les autres.`
            : undefined
        }
        onClose={() => setToDownload(null)}
        onStarted={() => void reload()}
      />
    </section>
  );
}

/** The summary offered first in the « Résumé » tab of this space's sessions. Summaries are
 *  made on demand only (ADR 0025): nothing runs on its own. */
function AutoSummaries({ spaceId, onError }: { spaceId: number; onError: (m: string | null) => void }) {
  const [actions, setActions] = useState<ActionInfo[]>([]);
  const [chosen, setChosen] = useState<SpaceAction[]>([]);
  useEffect(() => {
    Promise.all([api.actions(), api.spaceActions(spaceId)]).then(
      ([all, mine]) => {
        setActions(all);
        setChosen(mine);
      },
      (e: Error) => onError(e.message),
    );
  }, [spaceId, onError]);
  const offered = chosen.find((c) => c.auto_run)?.action_ref ?? "";
  const offer = async (ref: string) => {
    try {
      setChosen(await api.setOfferedAction(spaceId, ref || null));
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    }
  };
  return (
    <section className="cl-space__section">
      <Heading level={3}>Résumé proposé</Heading>
      <Text type="supporting">
        Celui qui est proposé d'abord dans l'onglet Résumé des séances de cet espace. Aucun résumé ne se fait tout seul : vous le lancez, avec le modèle de votre choix.
      </Text>
      <label className="cl-select cl-select--inline">
        <select aria-label="Résumé proposé" value={offered} onChange={(e) => void offer(e.target.value)}>
          <option value="">Aucun en particulier</option>
          {actions.map((a) => (
            <option key={a.ref} value={a.ref}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

type Attempt = (action: () => Promise<unknown>) => Promise<boolean>;

/** A value typed into in place, like a document (no box until hovered): Enter or leaving it
 *  saves, Escape gives back what was there; a name left empty gives it back too. A refused
 *  value stays typed and marked as not saved (the refusal said at the top of the page),
 *  until it is saved or given back. */
function InlineField({
  value,
  label,
  placeholder,
  required = false,
  className,
  onSave,
}: {
  value: string;
  label: string;
  placeholder?: string;
  /** Left empty, it gives back what was there (a name), else it is cleared (a role). */
  required?: boolean;
  className?: string;
  onSave: (value: string) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState(value);
  const [refused, setRefused] = useState(false);
  const cancel = useRef(false);
  useEffect(() => {
    setDraft(value);
    setRefused(false);
  }, [value]);
  return (
    <input
      className={`cl-inline ${className ?? ""}`}
      aria-label={label}
      aria-invalid={refused || undefined}
      title={refused ? "Pas enregistré : Échap rend ce qui était là." : undefined}
      value={draft}
      placeholder={placeholder}
      spellCheck
      lang="fr"
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        else if (e.key === "Escape") {
          cancel.current = true;
          e.currentTarget.blur();
        }
      }}
      onBlur={() => {
        const typed = draft.replace(/\s+/g, " ").trim();
        if (cancel.current || typed === value || (required && !typed)) {
          cancel.current = false;
          setDraft(value);
          setRefused(false);
          return;
        }
        void onSave(typed).then((done) => setRefused(!done));
      }}
    />
  );
}

/** The row that adds one more: « + Ajouter … », then a name typed in place (Enter adds and
 *  stays open for the next one, Escape or leaving it empty closes it). */
function AddRow({ label, placeholder, onAdd }: { label: string; placeholder: string; onAdd: (name: string) => Promise<boolean> }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  if (!open)
    return (
      <button type="button" className="cl-people__add" onClick={() => setOpen(true)}>
        <Plus size={16} strokeWidth={1.75} aria-hidden />
        {label}
      </button>
    );
  return (
    <div className="cl-people__add" data-open>
      <Plus size={16} strokeWidth={1.75} aria-hidden />
      <input
        className="cl-inline"
        aria-label={label}
        placeholder={placeholder}
        value={name}
        readOnly={adding}
        autoFocus
        onChange={(e) => setName(e.target.value)}
        onKeyDown={async (e) => {
          if (e.key === "Escape") {
            setName("");
            setOpen(false);
          } else if (e.key === "Enter" && name.trim() && !adding) {
            setAdding(true);
            if (await onAdd(name.trim())) setName("");
            setAdding(false);
          }
        }}
        onBlur={() => {
          if (!name.trim()) setOpen(false);
        }}
      />
    </div>
  );
}

type Filter = "all" | Person["kind"];

/** The space's people, members and guests in one list: each one's name and role typed into
 *  in place, a pill to make them a member or a guest, archived from their « … ». */
function PeopleSection({ spaceId, people, attempt }: { spaceId: number; people: Person[] | null; attempt: Attempt }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [showArchived, setShowArchived] = useState(false);
  const shown = (people ?? []).filter((p) => filter === "all" || p.kind === filter);
  const present = shown.filter((p) => !p.archived);
  const archived = shown.filter((p) => p.archived);
  return (
    <section className="cl-space__section">
      <div className="cl-space__bar">
        <Heading level={3}>Personnes</Heading>
        <div className="cl-filter" role="group" aria-label="Montrer">
          {(
            [
              ["all", "Tous"],
              ["member", "Membres"],
              ["guest", "Invités"],
            ] as const
          ).map(([key, label]) => (
            <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {people === null ? (
        <RowsSkeleton />
      ) : (
        <ul className="cl-people">
          {present.map((p) => (
            <PersonRow key={p.id} person={p} attempt={attempt} />
          ))}
          {showArchived && archived.map((p) => <PersonRow key={p.id} person={p} attempt={attempt} />)}
          <li>
            <AddRow
              label={filter === "guest" ? "Ajouter un invité" : "Ajouter une personne"}
              placeholder="Prénom"
              onAdd={(name) =>
                attempt(() => api.addPerson(spaceId, { name, kind: filter === "guest" ? "guest" : "member", role: null }))
              }
            />
          </li>
        </ul>
      )}
      {archived.length > 0 && (
        <div>
          <Button
            size="sm"
            variant="ghost"
            label={showArchived ? "Masquer les archivés" : `Voir ${plural(archived.length, "archivé", "archivés")}`}
            onClick={() => setShowArchived(!showArchived)}
          />
        </div>
      )}
    </section>
  );
}

function PersonRow({ person, attempt }: { person: Person; attempt: Attempt }) {
  const guest = person.kind === "guest";
  return (
    <li className="cl-people__row" data-archived={person.archived || undefined}>
      <span
        className="cl-avatar"
        style={{ background: speakerTint(person.color_slot), color: speakerInk(person.color_slot) }}
        aria-hidden
      >
        {person.name.trim().charAt(0).toUpperCase()}
      </span>
      <InlineField
        className="cl-people__name"
        label={`Nom de ${person.name}`}
        value={person.name}
        required
        onSave={(name) => attempt(() => api.updatePerson(person.id, { name }))}
      />
      <InlineField
        className="cl-people__role"
        label={`Rôle de ${person.name}`}
        value={person.role ?? ""}
        placeholder="Ajouter un rôle"
        onSave={(role) => attempt(() => api.updatePerson(person.id, { role }))}
      />
      <button
        type="button"
        className="cl-pill"
        title={guest ? "Passer membre" : "Passer invité"}
        onClick={() => void attempt(() => api.updatePerson(person.id, { kind: guest ? "member" : "guest" }))}
      >
        {guest ? "Invité" : "Membre"}
      </button>
      <span className="cl-people__more">
        <MoreMenu
          label={`Options de ${person.name}`}
          size="sm"
          alignment="end"
          items={[
            {
              label: guest ? "Passer membre" : "Passer invité",
              onClick: () => void attempt(() => api.updatePerson(person.id, { kind: guest ? "member" : "guest" })),
            },
            {
              label: person.archived ? "Désarchiver" : "Archiver",
              onClick: () => void attempt(() => api.updatePerson(person.id, { archived: !person.archived })),
            },
          ]}
        />
      </span>
    </li>
  );
}

function splitVariants(text: string): string[] {
  return text
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

/** The space's words, in the same list: each term and its known wrong spellings typed into
 *  in place, archived from its « … ». */
function GlossarySection({
  spaceId,
  entries,
  attempt,
}: {
  spaceId: number;
  entries: GlossaryEntry[] | null;
  attempt: Attempt;
}) {
  const [showArchived, setShowArchived] = useState(false);
  const present = (entries ?? []).filter((e) => !e.archived);
  const archived = (entries ?? []).filter((e) => e.archived);
  return (
    <section className="cl-space__section">
      <Heading level={3}>Glossaire</Heading>
      <Text type="supporting">
        Prénoms, jargon, exercices, personnages récurrents, sigles. Ils aident la transcription ; les graphies fautives
        connues sont signalées à la relecture.
      </Text>
      {entries === null ? (
        <RowsSkeleton />
      ) : (
        <ul className="cl-people">
          {present.map((e) => (
            <GlossaryRow key={e.id} entry={e} attempt={attempt} />
          ))}
          {showArchived && archived.map((e) => <GlossaryRow key={e.id} entry={e} attempt={attempt} />)}
          <li>
            <AddRow
              label="Ajouter un terme"
              placeholder="Terme"
              onAdd={(term) => attempt(() => api.addEntry(spaceId, { term, variants: [] }))}
            />
          </li>
        </ul>
      )}
      {archived.length > 0 && (
        <div>
          <Button
            size="sm"
            variant="ghost"
            label={showArchived ? "Masquer les archivés" : `Voir ${plural(archived.length, "archivé", "archivés")}`}
            onClick={() => setShowArchived(!showArchived)}
          />
        </div>
      )}
    </section>
  );
}

function GlossaryRow({ entry, attempt }: { entry: GlossaryEntry; attempt: Attempt }) {
  return (
    <li className="cl-people__row cl-people__row--term" data-archived={entry.archived || undefined}>
      <InlineField
        className="cl-people__name"
        label={`Terme ${entry.term}`}
        value={entry.term}
        required
        onSave={(term) => attempt(() => api.updateEntry(entry.id, { term }))}
      />
      <InlineField
        className="cl-people__role"
        label={`Graphies fautives de ${entry.term}`}
        value={entry.variants.join(", ")}
        placeholder="Ajouter des graphies fautives"
        onSave={(variants) => attempt(() => api.updateEntry(entry.id, { variants: splitVariants(variants) }))}
      />
      <span className="cl-people__more">
        <MoreMenu
          label={`Options de ${entry.term}`}
          size="sm"
          alignment="end"
          items={[
            {
              label: entry.archived ? "Désarchiver" : "Archiver",
              onClick: () => void attempt(() => api.updateEntry(entry.id, { archived: !entry.archived })),
            },
          ]}
        />
      </span>
    </li>
  );
}

/** A list while it is read: three rows' shapes. */
function RowsSkeleton() {
  return (
    <div className="cl-people cl-skeleton" aria-busy="true">
      {[0.3, 0.22, 0.26].map((w, i) => (
        <div key={i} className="cl-people__row">
          <Skeleton width={28} height={28} radius="rounded" index={i} />
          <Skeleton width={`${w * 100}%`} height={12} radius={1} index={i} />
        </div>
      ))}
    </div>
  );
}
