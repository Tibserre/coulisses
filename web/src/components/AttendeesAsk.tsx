import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Heading } from "@astryxdesign/core/Heading";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Minus, Plus } from "lucide-react";
import { Text } from "@astryxdesign/core/Text";
import type { Person, Session } from "../api.ts";
import { plural } from "../format.ts";
import { attendeesOf, secondsLeft, waitLeft } from "../processing.ts";

/** « Qui était là ? », above the processing of an import that waits for its people present
 *  (ADR 0069): first how many, with − and +; naming them is a choice (« Nommer les
 *  présents »), the others staying unnamed. They become the minimum of voices (P3). Each change is saved at once, so the
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
  language,
}: {
  session: Session;
  people: Person[];
  /** When the processing starts by itself (ISO time), measured by the service. */
  startsAt: string;
  /** Saves who was there (PUT /presents), then reads the session again, even on failure. */
  onSave: (ids: number[], unnamed: number | null) => Promise<void>;
  onLaunch: () => Promise<void>;
  /** Its language and the way to change it (ADR 0072), when it has something to say. */
  language?: ReactNode;
}) {
  const [ids, setIds] = useState<number[]>(session.attendee_ids);
  const [count, setCount] = useState(
    session.attendee_ids.length + (session.unnamed_attendees ?? 0),
  );
  const [naming, setNaming] = useState(session.attendee_ids.length > 0);
  const [error, setError] = useState<string | null>(null);
  // The saves, in order; none waiting: what is shown is the session's.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const waiting = useRef(0);
  // Bumped once no save waits any more: what is shown goes back to the session's, even when
  // the last save was refused and the session did not change.
  const [settled, setSettled] = useState(0);
  const savedIds = session.attendee_ids.join();
  // What was last asked, read by each click: two quick clicks add two (no stale render).
  const latest = useRef({ ids, count });
  useEffect(() => {
    if (waiting.current > 0) return;
    const fromSession = {
      ids: session.attendee_ids,
      count: session.attendee_ids.length + (session.unnamed_attendees ?? 0),
    };
    latest.current = fromSession;
    setIds(fromSession.ids);
    setCount(fromSession.count);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the ids, by value
  }, [savedIds, session.unnamed_attendees, settled]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const shown = people.filter(
    (p) => !p.archived || session.attendee_ids.includes(p.id),
  );
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
  const save = (nextIds: number[], nextCount: number) => {
    const next = attendeesOf(nextCount, nextIds);
    waiting.current += 1;
    const done = queue.current.then(() => onSave(next.ids, next.unnamed));
    queue.current = done
      .catch(() => undefined)
      .finally(() => {
        waiting.current -= 1;
        if (waiting.current === 0) setSettled((n) => n + 1);
      });
    return done;
  };
  const change = (
    make: (was: { ids: number[]; count: number }) => {
      ids: number[];
      count: number;
    },
  ) => {
    const asked = make(latest.current);
    const next = attendeesOf(asked.count, asked.ids);
    latest.current = { ids: next.ids, count: next.count };
    setIds(next.ids);
    setCount(next.count);
    void act(() => save(next.ids, next.count));
  };
  return (
    <section className="cl-ask cl-attendeesask">
      <Heading level={3}>Qui était là ?</Heading>
      <Text color="secondary">
        Au moins autant de voix seront cherchées. {waitLeft(left, count)}
      </Text>
      <div className="cl-stepper" role="group" aria-label="Nombre de présents">
        <IconButton
          label="Un présent de moins"
          icon={<Minus size={16} strokeWidth={1.75} />}
          variant="secondary"
          size="sm"
          isDisabled={count <= ids.length}
          onClick={() => change((was) => ({ ...was, count: was.count - 1 }))}
        />
        <span className="cl-stepper__value" aria-live="polite">
          {count ? plural(count, "présent", "présents") : "Aucun présent"}
        </span>
        <IconButton
          label="Un présent de plus"
          icon={<Plus size={16} strokeWidth={1.75} />}
          variant="secondary"
          size="sm"
          onClick={() => change((was) => ({ ...was, count: was.count + 1 }))}
        />
      </div>
      {shown.length > 0 &&
        (naming || ids.length > 0 ? (
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
                  change((was) => ({
                    ids: checked
                      ? [...was.ids, p.id]
                      : was.ids.filter((x) => x !== p.id),
                    count: was.count,
                  }))
                }
              />
            ))}
          </div>
        ) : (
          <div>
            <Button
              label="Nommer les présents"
              variant="ghost"
              size="sm"
              onClick={() => setNaming(true)}
            />
          </div>
        ))}
      {language}
      <div className="cl-ask__actions">
        <Button
          label={
            count
              ? `Lancer avec ${plural(count, "présent", "présents")}`
              : "Lancer le traitement"
          }
          variant="primary"
          clickAction={() =>
            act(async () => {
              await save(latest.current.ids, latest.current.count);
              await onLaunch();
            })
          }
        />
        {count > 0 && (
          <Button
            label="Lancer sans"
            variant="ghost"
            clickAction={() =>
              act(async () => {
                await save([], 0);
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
