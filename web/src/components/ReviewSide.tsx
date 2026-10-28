import { useEffect, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { Text } from "@astryxdesign/core/Text";
import type { CorrectedView, EditInfo, Person, Session } from "../api.ts";
import { formatDateTime } from "../format.ts";
import type { ReviewModel } from "../transcript.ts";

export function KeyFigures({
  view,
  model,
  dev,
}: {
  view: CorrectedView;
  model: ReviewModel;
  dev: boolean;
}) {
  const voices = model.speakers.filter((s) => s.label !== null).length;
  // The duration is said under the title; here, what the review is about.
  return (
    <dl className="cl-figures">
      <div>
        <dt>voix</dt>
        <dd>{voices}</dd>
      </div>
      <div>
        <dt>{view.turns.length > 1 ? "répliques" : "réplique"}</dt>
        <dd>{view.turns.length.toLocaleString("fr-FR")}</dd>
      </div>
      {dev && (
        <div>
          <dt>mots horodatés</dt>
          <dd>{Math.round(view.timed_share * 100)} %</dd>
        </div>
      )}
    </dl>
  );
}

/** Who was there, checked after the fact. It does not reprocess anything. */
export function Attendees({
  session,
  people,
  onSave,
  inline = false,
}: {
  session: Session;
  people: Person[];
  onSave: (ids: number[], unnamed: number | null) => Promise<void>;
  /** In its own small menu (ADR 0062): the list at once, without its heading. */
  inline?: boolean;
}) {
  const [ids, setIds] = useState<number[]>(session.attendee_ids);
  const [unnamed, setUnnamed] = useState<number | null>(
    session.unnamed_attendees,
  );
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setIds(session.attendee_ids);
    setUnnamed(session.unnamed_attendees);
  }, [session.attendee_ids, session.unnamed_attendees]);
  const changed =
    ids.slice().sort().join() !== session.attendee_ids.slice().sort().join() ||
    unnamed !== session.unnamed_attendees;
  const shown = people.filter(
    (p) => !p.archived || session.attendee_ids.includes(p.id),
  );
  const [open, setOpen] = useState(false);
  const count = session.attendee_ids.length + (session.unnamed_attendees ?? 0);
  const names = people
    .filter((p) => session.attendee_ids.includes(p.id))
    .map((p) => p.name);
  // People not read yet (or gone): said by their number, never left out silently.
  const known = names.length === session.attendee_ids.length;
  const unnamedText = session.unnamed_attendees
    ? `${session.unnamed_attendees} non ${session.unnamed_attendees > 1 ? "nommés" : "nommé"}`
    : null;
  const listed = known ? [...names, ...(unnamedText ? [unnamedText] : [])] : [];
  const sentence =
    listed.length > 1
      ? `${listed.slice(0, -1).join(", ")} et ${listed[listed.length - 1]}`
      : listed[0];
  if (!open && !changed && !inline) {
    return (
      <section>
        <div className="cl-side__line">
          <Heading level={3}>Présents</Heading>
          <Button
            size="sm"
            variant="ghost"
            label="Modifier"
            onClick={() => setOpen(true)}
          />
        </div>
        <Text type="supporting">
          {count === 0
            ? "Personne n'a été coché."
            : known
              ? sentence
              : `${count} ${count > 1 ? "présents" : "présent"}`}
        </Text>
      </section>
    );
  }
  return (
    <section>
      {!inline && (
        <div className="cl-side__line">
          <Heading level={3}>Présents</Heading>
          {!changed && (
            <Button
              size="sm"
              variant="ghost"
              label="Fermer"
              onClick={() => setOpen(false)}
            />
          )}
        </div>
      )}
      {shown.length === 0 ? (
        <Text type="supporting">
          Aucune personne dans l'espace « {session.space_name} » : ajoutez-en
          depuis la page Espaces, ou en nommant une voix.
        </Text>
      ) : (
        <div className="cl-checklist">
          {shown.map((p) => (
            <CheckboxInput
              key={p.id}
              label={p.name}
              description={
                p.kind === "guest" ? "invité" : (p.role ?? undefined)
              }
              value={ids.includes(p.id)}
              onChange={(checked) =>
                setIds((before) =>
                  checked
                    ? [...before, p.id]
                    : before.filter((x) => x !== p.id),
                )
              }
            />
          ))}
        </div>
      )}
      <div style={{ width: 200 }}>
        <NumberInput
          label="Présents non nommés"
          value={unnamed}
          isOptional
          onChange={(v) =>
            setUnnamed(Number.isFinite(v) && v >= 1 ? Math.round(v) : null)
          }
        />
      </div>
      {changed && (
        <div>
          <Button
            size="sm"
            variant="primary"
            label="Enregistrer les présents"
            clickAction={async () => {
              try {
                await onSave(ids, unnamed);
                setError(null);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          />
          <Text type="supporting" as="p">
            Le traitement déjà fait n'est pas relancé.
          </Text>
        </div>
      )}
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
    </section>
  );
}

/** Every correction, latest first; undone ones stay listed (nothing is erased). */
export function CorrectionsHistory({
  edits,
  onUndo,
  onRedo,
}: {
  edits: EditInfo[];
  onUndo: (id: number) => Promise<void>;
  onRedo: (id: number) => Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  if (edits.length === 0) return null;
  const latest = [...edits].reverse();
  const listed = all ? latest : latest.slice(0, SHOWN_EDITS);
  const run = (action: () => Promise<void>) => async () => {
    try {
      await action();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section>
      <div className="cl-side__line">
        <Heading level={3}>Corrections</Heading>
        <Text type="supporting">{edits.length}</Text>
      </div>
      <ol className="cl-history">
        {listed.map((e) => (
          <li key={e.id} data-reverted={e.reverted || undefined}>
            <span className="cl-history__text">
              <Text hasStrikethrough={e.reverted}>{e.description}</Text>
              <Text type="supporting">{formatDateTime(e.created_at)}</Text>
            </span>
            {e.reverted && e.redone ? (
              <Text type="supporting">rétablie plus loin</Text>
            ) : e.reverted ? (
              <Button
                size="sm"
                variant="ghost"
                label="Rétablir"
                clickAction={run(() => onRedo(e.id))}
              />
            ) : (
              <Button
                size="sm"
                variant="ghost"
                label="Annuler"
                clickAction={run(() => onUndo(e.id))}
              />
            )}
          </li>
        ))}
      </ol>
      {latest.length > SHOWN_EDITS && (
        <div>
          <Button
            size="sm"
            variant="ghost"
            label={
              all
                ? "N'afficher que les dernières"
                : `Voir les ${latest.length - SHOWN_EDITS} autres`
            }
            onClick={() => setAll(!all)}
          />
        </div>
      )}
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
    </section>
  );
}

/** The corrections listed at first: the latest; the others on demand (none hidden). */
const SHOWN_EDITS = 3;
