import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { Popover } from "@astryxdesign/core/Popover";
import { Check, ChevronDown, Mic } from "lucide-react";
import type { AppInfo, Project, RecordingState, Session, Space } from "../api.ts";
import type { Way } from "../components/NewSessionDialog.tsx";
import { Badge } from "@astryxdesign/core/Badge";
import { JobBadge } from "../components/JobBadge.tsx";
import { PurgeBanner } from "../components/PurgeBanner.tsx";
import { formatClock, formatDate, formatDuration, plural } from "../format.ts";
import { rememberSpace, rememberedSpace, sessionHref, sessionName, startSpace } from "../library.ts";
import { formatDay, takeMessage } from "../retention.ts";

const RECENT = 6;
/** What the main pane shows with no session open. First what one comes for: record a
 *  session, in a space (the one chosen last, else the latest session's), or import a file.
 *  Then what needs attention (the service, an interrupted recording, a purge coming), the
 *  sessions being recorded or processed (or whose processing failed), and the latest few:
 *  the rest is in the side column. */
export function HomePage({
  sessions,
  spaces,
  projects,
  info,
  recording,
  error,
  onNewSession,
}: {
  sessions: Session[] | null;
  spaces: Space[];
  projects: Project[];
  info: AppInfo | null;
  recording: RecordingState | null;
  error: string | null;
  onNewSession: (spaceId: number | null, way: Way) => void;
}) {
  // Left by a session page that just deleted its session (what stayed on the disk).
  const [message, setMessage] = useState<string | null>(() => takeMessage());
  const sorted = [...(sessions ?? [])].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
  // What is going on first; then the latest.
  const busy = (s: Session) =>
    s.id === recording?.session_id || s.job_state === "queued" || s.job_state === "running" || s.job_state === "failed";
  const ongoing = sorted.filter(busy);
  const recent = sorted.filter((s) => !busy(s)).slice(0, RECENT);
  const projectName = new Map(projects.map((p) => [p.id, p.name]));

  const open = spaces.filter((s) => !s.archived);
  const [chosen, setChosen] = useState<number | null>(rememberedSpace);
  const spaceId = startSpace(spaces, sorted, chosen);

  return (
    <main className="cl-home">
      {error && <Banner status="error" title="Le service ne répond pas" description={error} />}
      {info?.processing_error && (
        <Banner
          status="error"
          title="Le traitement en tâche de fond a rencontré une erreur"
          description={`${info.processing_error}. Il réessaie toutes les deux secondes ; si le message reste, relancez Coulisses.`}
        />
      )}
      {message && (
        <Banner status="warning" title="Suppression incomplète" description={message} isDismissable onDismiss={() => setMessage(null)} />
      )}
      {info && info.recovery_problems.length > 0 && (
        <Banner status="warning" title="À vérifier depuis le dernier lancement" collapsible={false}>
          <ul className="cl-list">
            {info.recovery_problems.map((p) => (
              <li key={p}>
                <Text>{p}</Text>
              </li>
            ))}
          </ul>
        </Banner>
      )}
      <PurgeBanner />

      <section className="cl-start" aria-label="Commencer une séance">
        {recording ? (
          <>
            <a className="cl-start__button" data-live href="#/enregistrement" aria-label="Revenir à l'enregistrement">
              <span className="cl-start__dot" aria-hidden />
            </a>
            <p className="cl-start__title">
              {recording.state === "paused" ? "Enregistrement en pause" : "Enregistrement en cours"}
            </p>
            <Text type="supporting">
              {formatClock(recording.elapsed_s)} avec {recording.device} ·{" "}
              <a className="cl-linkbtn" href="#/enregistrement">
                y revenir
              </a>
            </Text>
          </>
        ) : (
          <>
            <button
              type="button"
              className="cl-start__button"
              aria-label="Enregistrer une séance"
              onClick={() => onNewSession(spaceId, "enregistrer")}
            >
              <Mic size={28} strokeWidth={1.75} aria-hidden />
            </button>
            <p className="cl-start__title">
              {open.length > 1 ? (
                <>
                  Enregistrer dans{" "}
                  <SpacePicker
                    spaces={open}
                    chosen={spaceId}
                    onChoose={(id) => {
                      setChosen(id);
                      rememberSpace(id);
                    }}
                  />
                </>
              ) : open.length === 1 ? (
                `Enregistrer dans ${open[0].name}`
              ) : (
                "Enregistrer une séance"
              )}
            </p>
            <Text type="supporting">
              ⌘N ·{" "}
              <button type="button" className="cl-linkbtn" onClick={() => onNewSession(spaceId, "importer")}>
                ou importer un fichier
              </button>
            </Text>
          </>
        )}
      </section>

      {ongoing.length > 0 && (
        <section className="cl-home__recent">
          <Heading level={2}>En cours</Heading>
          <SessionList sessions={ongoing} projectName={projectName} recordingId={recording?.session_id ?? null} />
        </section>
      )}
      {recent.length > 0 && (
        <section className="cl-home__recent">
          <Heading level={2}>Récemment</Heading>
          <SessionList sessions={recent} projectName={projectName} recordingId={recording?.session_id ?? null} />
        </section>
      )}
    </main>
  );
}

function SessionList({
  sessions,
  projectName,
  recordingId,
}: {
  sessions: Session[];
  projectName: Map<number, string>;
  recordingId: string | null;
}) {
  return (
    <ul className="cl-sessions">
      {sessions.map((s) => {
        const present = s.attendee_ids.length + (s.unnamed_attendees ?? 0);
        const where = [s.space_name, s.project_id != null ? projectName.get(s.project_id) : null]
          .filter(Boolean)
          .join(" · ");
        return (
          <li key={s.id}>
            <a className="cl-sessions__item" href={s.id === recordingId ? "#/enregistrement" : sessionHref(s.id)}>
              <span className="cl-sessions__what">
                <span className="cl-sessions__title">{sessionName(s)}</span>
                <Text type="supporting">
                  {where} · {formatDuration(s.duration_s)}
                  {present ? ` · ${plural(present, "présent", "présents")}` : ""}
                </Text>
              </span>
              <span className="cl-sessions__badges">
                {s.id === recordingId && <Badge variant="info" label="Enregistrement en cours" />}
                {s.audio.state === "announced" && s.audio.purge_on && (
                  <Badge variant="warning" label={`Suppression de l'audio le ${formatDay(s.audio.purge_on)}`} />
                )}
                {s.audio.state === "removed" && <Badge variant="neutral" label="Audio supprimé" />}
                {s.audio.state === "kept" && <Badge variant="neutral" label="Audio gardé" />}
                {/* « Prête » goes without saying: only what is not. */}
                {s.id !== recordingId && s.job_state !== "done" && <JobBadge state={s.job_state} />}
              </span>
              <Text type="supporting" className="cl-sessions__when">
                {formatDate(s.recorded_at)}
              </Text>
            </a>
          </li>
        );
      })}
    </ul>
  );
}

/** The space a recording goes to, chosen in place: its name, underlined, opens the list of
 *  the open spaces, the chosen one ticked. */
function SpacePicker({
  spaces,
  chosen,
  onChoose,
}: {
  spaces: Space[];
  chosen: number | null;
  onChoose: (id: number) => void;
}) {
  const [isOpen, setOpen] = useState(false);
  const list = useRef<HTMLUListElement>(null);
  const name = spaces.find((s) => s.id === chosen)?.name ?? "";
  // Opened: the focus on the chosen one; ↑ and ↓ go from one to the next.
  useEffect(() => {
    if (!isOpen) return;
    const timer = window.setTimeout(() => {
      const items = [...(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
      (items.find((b) => b.hasAttribute("aria-current")) ?? items[0])?.focus();
    });
    return () => window.clearTimeout(timer);
  }, [isOpen]);
  const move = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = [...(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = e.key === "ArrowDown" ? Math.min(items.length - 1, at + 1) : Math.max(0, at - 1);
    items[next]?.focus();
  };
  return (
    <Popover
      isOpen={isOpen}
      onOpenChange={setOpen}
      hasAutoFocus={false}
      label="Espace de la séance"
      placement="below"
      alignment="center"
      width={280}
      padding={1}
      content={
        <ul ref={list} className="cl-spacepick" aria-label="Espaces" onKeyDown={move}>
          {spaces.map((s) => {
            return (
              <li key={s.id}>
                <button
                  type="button"
                  className="cl-spacepick__item"
                  aria-current={s.id === chosen || undefined}
                  onClick={() => {
                    onChoose(s.id);
                    setOpen(false);
                  }}
                >
                  <span className="cl-spacepick__what">{s.name}</span>
                  {s.id === chosen && <Check size={16} strokeWidth={1.75} aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
      }
    >
      <button type="button" className="cl-start__space" aria-label={`Espace : ${name}. Changer`}>
        {name}
        <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
      </button>
    </Popover>
  );
}
