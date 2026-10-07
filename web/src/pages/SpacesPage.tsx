import { useCallback, useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import {
  api,
  type ActionInfo,
  type GlossaryEntry,
  type Person,
  type Space,
  type SpaceAction,
  type SpaceTemplate,
} from "../api.ts";
import { speakerInk } from "../theme/shared.ts";

/** A space's settings (a troupe, a team, a client; ADR 0020), opened from its « … » menu
 *  in the side column: its name, its people, its glossary, the summary it offers first.
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
      <Heading level={2}>{space ? `Paramètres de ${space.name}` : "Paramètres de l'espace"}</Heading>
      {error && <Banner status="error" title="Action refusée" description={error} />}
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
  const [name, setName] = useState(space.name);
  const [people, setPeople] = useState<Person[]>([]);
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);

  const load = useCallback(async () => {
    const [p, g] = await Promise.all([
      api.people(space.id),
      api.glossary(space.id),
    ]);
    setPeople(p);
    setGlossary(g);
  }, [space.id]);
  useEffect(() => {
    void load().catch((e: Error) => onError(e.message));
  }, [load, onError]);

  const act = (action: () => Promise<unknown>) => async () => {
    try {
      await action();
      await load();
      await onChanged();
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <div className="cl-space">
      <div className="cl-space__head">
        <TextInput
          label="Nom de l'espace"
          value={name}
          onChange={setName}
          onEnter={() => void act(() => api.updateSpace(space.id, { name }))()}
        />
        {name !== space.name && (
          <Button
            label="Renommer"
            clickAction={act(() => api.updateSpace(space.id, { name }))}
          />
        )}
        <Button
          variant="ghost"
          label={space.archived ? "Désarchiver" : "Archiver l'espace"}
          clickAction={act(() =>
            api.updateSpace(space.id, { archived: !space.archived }),
          )}
        />
      </div>

      <Switch
        label="Reconnaître les voix d'une séance à l'autre"
        description="Désactivé, aucune signature vocale n'est créée : on nomme les voix à chaque séance. Activé, l'application pourra plus tard reconnaître les personnes de cet espace."
        value={space.voice_recognition}
        onChange={(on) =>
          void act(() => api.updateSpace(space.id, { voice_recognition: on }))()
        }
      />

      <PeopleSection
        title="Membres"
        kind="member"
        spaceId={space.id}
        people={people.filter((p) => p.kind === "member")}
        act={act}
      />
      <PeopleSection
        title="Invités"
        kind="guest"
        spaceId={space.id}
        people={people.filter((p) => p.kind === "guest")}
        act={act}
      />
      <GlossarySection spaceId={space.id} entries={glossary} act={act} />
      <AutoSummaries spaceId={space.id} onError={onError} />
    </div>
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
      <label className="cl-select">
        <span>Résumé proposé</span>
        <select value={offered} onChange={(e) => void offer(e.target.value)}>
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

type Act = (action: () => Promise<unknown>) => () => Promise<void>;

function PeopleSection({
  title,
  kind,
  spaceId,
  people,
  act,
}: {
  title: string;
  kind: Person["kind"];
  spaceId: number;
  people: Person[];
  act: Act;
}) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const add = act(async () => {
    await api.addPerson(spaceId, { name, kind, role: role || null });
    setName("");
    setRole("");
  });
  return (
    <section className="cl-space__section">
      <Heading level={3}>{title}</Heading>
      {people.length === 0 && (
        <Text type="supporting">Personne pour l'instant.</Text>
      )}
      <ul className="cl-rows">
        {people.map((p) => (
          <PersonRow key={p.id} person={p} act={act} />
        ))}
      </ul>
      <div className="cl-rows__add">
        <TextInput
          label="Nom"
          value={name}
          onChange={setName}
          size="sm"
          onEnter={() => void add()}
        />
        <TextInput
          label="Rôle"
          placeholder={
            kind === "member"
              ? "coach, comédienne, cheffe de projet…"
              : "facultatif"
          }
          value={role}
          onChange={setRole}
          size="sm"
          onEnter={() => void add()}
        />
        <Button
          size="sm"
          label="Ajouter"
          clickAction={add}
          isDisabled={!name.trim()}
        />
      </div>
    </section>
  );
}

function PersonRow({ person, act }: { person: Person; act: Act }) {
  const [name, setName] = useState(person.name);
  const [role, setRole] = useState(person.role ?? "");
  const changed = name !== person.name || role !== (person.role ?? "");
  return (
    <li className="cl-rows__item" data-archived={person.archived || undefined}>
      <span
        className="cl-dot"
        style={{ background: speakerInk(person.color_slot) }}
        aria-hidden
      />
      <TextInput
        label="Nom"
        isLabelHidden
        value={name}
        onChange={setName}
        size="sm"
      />
      <TextInput
        label="Rôle"
        isLabelHidden
        placeholder="rôle"
        value={role}
        onChange={setRole}
        size="sm"
      />
      {changed && (
        <Button
          size="sm"
          label="Enregistrer"
          clickAction={act(() => api.updatePerson(person.id, { name, role }))}
        />
      )}
      <Button
        size="sm"
        variant="ghost"
        label={person.kind === "guest" ? "Passer membre" : "Passer invité"}
        clickAction={act(() =>
          api.updatePerson(person.id, {
            kind: person.kind === "guest" ? "member" : "guest",
          }),
        )}
      />
      <Button
        size="sm"
        variant="ghost"
        label={person.archived ? "Désarchiver" : "Archiver"}
        clickAction={act(() =>
          api.updatePerson(person.id, { archived: !person.archived }),
        )}
      />
    </li>
  );
}

function splitVariants(text: string): string[] {
  return text
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function GlossarySection({
  spaceId,
  entries,
  act,
}: {
  spaceId: number;
  entries: GlossaryEntry[];
  act: Act;
}) {
  const [term, setTerm] = useState("");
  const [variants, setVariants] = useState("");
  const add = act(async () => {
    await api.addEntry(spaceId, { term, variants: splitVariants(variants) });
    setTerm("");
    setVariants("");
  });
  return (
    <section className="cl-space__section">
      <Heading level={3}>Glossaire</Heading>
      <Text type="supporting">
        Prénoms, jargon, exercices, personnages récurrents, sigles. Ils aident
        la transcription, et les graphies fautives connues sont signalées
        pendant la relecture avec la bonne orthographe.
      </Text>
      <ul className="cl-rows">
        {entries.map((e) => (
          <GlossaryRow key={e.id} entry={e} act={act} />
        ))}
      </ul>
      <div className="cl-rows__add">
        <TextInput
          label="Terme"
          value={term}
          onChange={setTerm}
          size="sm"
          onEnter={() => void add()}
        />
        <TextInput
          label="Graphies fautives"
          placeholder="Kathy, Katie"
          value={variants}
          onChange={setVariants}
          size="sm"
          onEnter={() => void add()}
        />
        <Button
          size="sm"
          label="Ajouter"
          clickAction={add}
          isDisabled={!term.trim()}
        />
      </div>
    </section>
  );
}

function GlossaryRow({ entry, act }: { entry: GlossaryEntry; act: Act }) {
  const [term, setTerm] = useState(entry.term);
  const [variants, setVariants] = useState(entry.variants.join(", "));
  const changed = term !== entry.term || variants !== entry.variants.join(", ");
  return (
    <li className="cl-rows__item" data-archived={entry.archived || undefined}>
      <TextInput
        label="Terme"
        isLabelHidden
        value={term}
        onChange={setTerm}
        size="sm"
      />
      <TextInput
        label="Graphies fautives"
        isLabelHidden
        placeholder="graphies fautives"
        value={variants}
        onChange={setVariants}
        size="sm"
      />
      {changed && (
        <Button
          size="sm"
          label="Enregistrer"
          clickAction={act(() =>
            api.updateEntry(entry.id, {
              term,
              variants: splitVariants(variants),
            }),
          )}
        />
      )}
      <Button
        size="sm"
        variant="ghost"
        label={entry.archived ? "Désarchiver" : "Archiver"}
        clickAction={act(() =>
          api.updateEntry(entry.id, { archived: !entry.archived }),
        )}
      />
    </li>
  );
}
