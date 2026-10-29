import { useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { Text } from "@astryxdesign/core/Text";
import type { Person, Session } from "../api.ts";
import { plural } from "../format.ts";
import { secondsLeft, waitLeft } from "../processing.ts";

/** « Qui était là ? », above the processing of an import that waits for its people present
 *  (ADR 0069): they become the minimum of voices (P3). Each change is saved at once, so the
 *  processing that starts by itself when the wait is over takes them too: one save after the
 *  other, the last state always the one kept. What is shown follows the session (changed
 *  above the title too, or put back after a failed save). Launched with them, or without
 *  (which unchecks them). */
export function AttendeesAsk({
  session,
  people,
  startsAt,
  onSave,
  onLaunch,
}: {
  session: Session;
  people: Person[];
  /** When the processing starts by itself (ISO time), measured by the service. */
  startsAt: string;
  /** Saves who was there (PUT /presents), then reads the session again, even on failure. */
  onSave: (ids: number[], unnamed: number | null) => Promise<void>;
  onLaunch: () => Promise<void>;
}) {
  const [ids, setIds] = useState<number[]>(session.attendee_ids);
  const [unnamed, setUnnamed] = useState<number | null>(
    session.unnamed_attendees,
  );
  const [error, setError] = useState<string | null>(null);
  // The saves, in order; none waiting: what is shown is the session's.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const waiting = useRef(0);
  const savedIds = session.attendee_ids.join();
  useEffect(() => {
    if (waiting.current > 0) return;
    setIds(session.attendee_ids);
    setUnnamed(session.unnamed_attendees);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the ids, by value
  }, [savedIds, session.unnamed_attendees]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const shown = people.filter(
    (p) => !p.archived || session.attendee_ids.includes(p.id),
  );
  const total = ids.length + (unnamed ?? 0);
  const left = secondsLeft(startsAt, now);
  const act = async (what: () => Promise<void>) => {
    setError(null);
    try {
      await what();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  /** Saved after those before it; its failure is said, and the session read again. */
  const save = (nextIds: number[], nextUnnamed: number | null) => {
    waiting.current += 1;
    const done = queue.current.then(() => onSave(nextIds, nextUnnamed));
    queue.current = done
      .catch(() => undefined)
      .finally(() => {
        waiting.current -= 1;
      });
    return done;
  };
  const change = (nextIds: number[], nextUnnamed: number | null) => {
    setIds(nextIds);
    setUnnamed(nextUnnamed);
    void act(() => save(nextIds, nextUnnamed));
  };
  return (
    <section className="cl-ask cl-attendeesask">
      <Heading level={3}>Qui était là ?</Heading>
      <Text color="secondary">
        Au moins autant de voix seront cherchées. {waitLeft(left, total)}
      </Text>
      {shown.length === 0 ? (
        <Text type="supporting">
          Personne dans l'espace « {session.space_name} » pour l'instant :
          donnez leur nombre ci-dessous.
        </Text>
      ) : (
        <div className="cl-checklist cl-checklist--columns">
          {shown.map((p) => (
            <CheckboxInput
              key={p.id}
              label={p.name}
              description={
                p.kind === "guest" ? "invité" : (p.role ?? undefined)
              }
              value={ids.includes(p.id)}
              onChange={(checked) =>
                change(
                  checked ? [...ids, p.id] : ids.filter((x) => x !== p.id),
                  unnamed,
                )
              }
            />
          ))}
        </div>
      )}
      <div style={{ width: 200 }}>
        <NumberInput
          label={shown.length === 0 ? "Présents" : "Présents non nommés"}
          value={unnamed}
          isOptional
          onChange={(v) =>
            change(ids, Number.isFinite(v) && v >= 1 ? Math.round(v) : null)
          }
        />
      </div>
      <div className="cl-ask__actions">
        <Button
          label={
            total
              ? `Lancer avec ${plural(total, "présent", "présents")}`
              : "Lancer le traitement"
          }
          variant="primary"
          clickAction={() =>
            act(async () => {
              await save(ids, unnamed);
              await onLaunch();
            })
          }
        />
        {total > 0 && (
          <Button
            label="Lancer sans"
            variant="ghost"
            clickAction={() =>
              act(async () => {
                await save([], null);
                await onLaunch();
              })
            }
          />
        )}
      </div>
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
    </section>
  );
}
