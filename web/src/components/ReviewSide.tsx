import { useEffect, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { Text } from "@astryxdesign/core/Text";
import type { CorrectedView, EditInfo, Person, Session } from "../api.ts";
import { formatDateTime, formatDuration, plural } from "../format.ts";
import type { ReviewModel } from "../transcript.ts";
import { speakerTitle } from "../transcript.ts";
import { inkOf } from "./TranscriptView.tsx";

export function KeyFigures({
  view,
  model,
  duration,
  dev,
}: {
  view: CorrectedView;
  model: ReviewModel;
  duration: number | null;
  dev: boolean;
}) {
  const voices = model.speakers.filter((s) => s.label !== null).length;
  return (
    <dl className="cl-figures">
      <div>
        <dt>Durée</dt>
        <dd>{formatDuration(duration)}</dd>
      </div>
      <div>
        <dt>Voix</dt>
        <dd>{voices}</dd>
      </div>
      <div>
        <dt>Répliques</dt>
        <dd>{view.turns.length}</dd>
      </div>
      {dev && (
        <div>
          <dt>Mots horodatés</dt>
          <dd>{Math.round(view.timed_share * 100)} %</dd>
        </div>
      )}
    </dl>
  );
}

export function Participants({ model }: { model: ReviewModel }) {
  const total = model.speakers.reduce((sum, s) => sum + s.seconds, 0) || 1;
  const unnamed = model.speakers.filter(
    (s) => !s.named && s.label !== null,
  ).length;
  return (
    <section>
      <Heading level={3}>Participants</Heading>
      <Text type="supporting">
        {unnamed > 0
          ? `${plural(unnamed, "voix reste", "voix restent")} à nommer : cliquez sur un nom dans le transcript, ou appuyez sur N pendant l'écoute.`
          : "Toutes les voix sont nommées."}
      </Text>
      <ul className="cl-participants">
        {model.speakers.map((s) => (
          <li key={s.label ?? "inconnu"}>
            <span
              className="cl-name"
              data-unnamed={!s.named || undefined}
              style={{ color: inkOf(s) }}
            >
              {speakerTitle(s)}
            </span>
            <span className="cl-share" aria-hidden>
              <span
                style={{
                  width: `${(100 * s.seconds) / total}%`,
                  background: inkOf(s),
                }}
              />
            </span>
            <Text type="supporting">
              {Math.round((100 * s.seconds) / total)} %
            </Text>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Who was there, checked after the fact. It does not reprocess anything. */
export function Attendees({
  session,
  people,
  onSave,
}: {
  session: Session;
  people: Person[];
  onSave: (ids: number[], unnamed: number | null) => Promise<void>;
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
  return (
    <section>
      <Heading level={3}>Présents</Heading>
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
  if (edits.length === 0) return null;
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
      <Heading level={3}>Corrections</Heading>
      <ol className="cl-history">
        {[...edits].reverse().map((e) => (
          <li key={e.id} data-reverted={e.reverted || undefined}>
            <span className="cl-history__text">
              <Text hasStrikethrough={e.reverted}>{e.description}</Text>
              <Text type="supporting">{formatDateTime(e.created_at)}</Text>
            </span>
            {e.reverted ? (
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
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
    </section>
  );
}
