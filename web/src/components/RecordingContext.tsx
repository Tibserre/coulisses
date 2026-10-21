import { useEffect, useState, type ReactNode } from "react";
import { Popover } from "@astryxdesign/core/Popover";
import { Check, ChevronDown } from "lucide-react";
import {
  api,
  type Person,
  type Project,
  type Session,
  type Space,
} from "../api.ts";

/** Where a recording goes and who is there, changed while it runs (spec §7.2, ADR 0056):
 *  the space, the project, the people checked. A recording starts in one gesture, in the
 *  space selected; this is where it is put right. Each one is a quiet label that opens its
 *  list, floating under it: nothing moves. */
export function RecordingContext({
  session,
  spaces,
  projects,
  onChanged,
  onError,
}: {
  session: Session;
  spaces: Space[];
  projects: Project[];
  onChanged: (session: Session) => void;
  onError: (message: string) => void;
}) {
  const [people, setPeople] = useState<Person[] | null>(null);
  /** People unchecked by a move to another space: said, never silent (P8). */
  const [unchecked, setUnchecked] = useState<string[]>([]);
  useEffect(() => {
    setPeople(null);
    api.people(session.space_id).then(
      (all) => setPeople(all.filter((p) => !p.archived)),
      (e: Error) => onError(e.message),
    );
  }, [session.space_id, onError]);

  const run = async (step: () => Promise<Session>) => {
    try {
      onChanged(await step());
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const space = spaces.find((s) => s.id === session.space_id);
  const ownProjects = projects.filter(
    (p) => p.space_id === session.space_id && !p.archived,
  );
  const project = ownProjects.find((p) => p.id === session.project_id);
  const checked = new Set(session.attendee_ids);
  const names = (people ?? [])
    .filter((p) => checked.has(p.id))
    .map((p) => p.name);

  return (
    <div className="cl-rec__context">
      <ChipMenu label={space?.name ?? "Espace"} title="Espace">
        {(close) =>
          spaces
            .filter((s) => !s.archived)
            .map((s) => (
              <Choice
                key={s.id}
                isCurrent={s.id === session.space_id}
                onPick={() => {
                  close();
                  if (s.id === session.space_id) return;
                  void (async () => {
                    try {
                      const moved = await api.moveSession(session.id, s.id);
                      // Said once done, by the service: who was unchecked, archived ones too.
                      setUnchecked(moved.unchecked);
                      onChanged(moved.session);
                    } catch (e) {
                      onError((e as Error).message);
                    }
                  })();
                }}
              >
                {s.name}
              </Choice>
            ))
        }
      </ChipMenu>
      <ChipMenu label={project?.name ?? "Aucun projet"} title="Projet">
        {(close) => [
          <Choice
            key="aucun"
            isCurrent={session.project_id === null}
            onPick={() => {
              close();
              void run(() => api.setSessionProject(session.id, null));
            }}
          >
            Aucun projet
          </Choice>,
          ...ownProjects.map((p) => (
            <Choice
              key={p.id}
              isCurrent={p.id === session.project_id}
              onPick={() => {
                close();
                void run(() => api.setSessionProject(session.id, p.id));
              }}
            >
              {p.name}
            </Choice>
          )),
        ]}
      </ChipMenu>
      <ChipMenu
        label={
          checked.size === 0
            ? "Présents"
            : checked.size === 1
              ? (names[0] ?? "1 présent")
              : `${checked.size} présents`
        }
        title="Présents"
        prefix={checked.size === 0 ? "+ " : ""}
      >
        {() =>
          people === null
            ? []
            : people.length === 0
              ? [
                  <li key="vide" className="cl-nameedit__empty">
                    Personne dans cet espace pour l'instant.
                  </li>,
                ]
              : people.map((p) => (
                  <Choice
                    key={p.id}
                    isCurrent={checked.has(p.id)}
                    onPick={() => {
                      const next = checked.has(p.id)
                        ? session.attendee_ids.filter((id) => id !== p.id)
                        : [...session.attendee_ids, p.id];
                      setUnchecked([]);
                      void run(() =>
                        api.setAttendees(
                          session.id,
                          next,
                          session.unnamed_attendees,
                        ),
                      );
                    }}
                  >
                    {p.name}
                  </Choice>
                ))
        }
      </ChipMenu>
      {unchecked.length > 0 && (
        <span className="cl-rec__said" role="status">
          Décochés en changeant d'espace : {unchecked.join(", ")}.
        </span>
      )}
    </div>
  );
}

/** A quiet label that opens its list below it, floating (no native select). */
function ChipMenu({
  label,
  title,
  prefix = "",
  children,
}: {
  label: string;
  title: string;
  prefix?: string;
  children: (close: () => void) => ReactNode[];
}) {
  const [isOpen, setOpen] = useState(false);
  return (
    <Popover
      isOpen={isOpen}
      onOpenChange={setOpen}
      label={title}
      placement="below"
      alignment="start"
      width={260}
      padding={1}
      content={
        <ul className="cl-spacepick" aria-label={title}>
          {children(() => setOpen(false))}
        </ul>
      }
    >
      <button
        type="button"
        className="cl-chip"
        aria-label={`${title} : ${label}. Changer`}
      >
        {prefix}
        {label}
        <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
      </button>
    </Popover>
  );
}

function Choice({
  isCurrent,
  onPick,
  children,
}: {
  isCurrent: boolean;
  onPick: () => void;
  children: ReactNode;
}) {
  return (
    <li>
      <button
        type="button"
        className="cl-spacepick__item"
        aria-current={isCurrent || undefined}
        onClick={onPick}
      >
        <span>{children}</span>
        {isCurrent && <Check size={16} strokeWidth={1.75} aria-hidden />}
      </button>
    </li>
  );
}
