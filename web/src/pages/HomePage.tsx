import { useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { FileAudio, Plus } from "lucide-react";
import type { AppInfo, Project, RecordingState, Session } from "../api.ts";
import { Badge } from "@astryxdesign/core/Badge";
import { JobBadge } from "../components/JobBadge.tsx";
import { PurgeBanner } from "../components/PurgeBanner.tsx";
import { formatClock, formatDate, formatDuration, plural } from "../format.ts";
import { byPeriod, sessionHref, sessionName } from "../library.ts";
import { formatDay, takeMessage } from "../retention.ts";

const RECENT = 12;

/** What the main pane shows with no session open: what needs attention (the service, an
 *  interrupted recording, a purge coming), the sessions being recorded or processed (or
 *  whose processing failed), then the latest of every space, by period. */
export function HomePage({
  sessions,
  projects,
  info,
  recording,
  error,
  onNewSession,
}: {
  sessions: Session[] | null;
  projects: Project[];
  info: AppInfo | null;
  recording: RecordingState | null;
  error: string | null;
  onNewSession: () => void;
}) {
  // Left by a session page that just deleted its session (what stayed on the disk).
  const [message, setMessage] = useState<string | null>(() => takeMessage());
  const sorted = [...(sessions ?? [])].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
  // What is going on first; then the latest, by period.
  const busy = (s: Session) =>
    s.id === recording?.session_id || s.job_state === "queued" || s.job_state === "running" || s.job_state === "failed";
  const ongoing = sorted.filter(busy);
  const groups = byPeriod(sorted.filter((s) => !busy(s)).slice(0, RECENT));
  const projectName = new Map(projects.map((p) => [p.id, p.name]));
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
      {recording && (
        <Banner
          status="info"
          title={recording.state === "paused" ? "Enregistrement en pause" : "Enregistrement en cours"}
          description={`${formatClock(recording.elapsed_s)} enregistrées avec ${recording.device}.`}
          endContent={<Button size="sm" label="Y revenir" onClick={() => (window.location.hash = "#/enregistrement")} />}
        />
      )}
      <PurgeBanner />
      {sessions !== null && sessions.length === 0 ? (
        <section className="cl-home__recent">
          <Heading level={2}>Bienvenue</Heading>
          <div className="cl-empty">
            <FileAudio size={40} strokeWidth={1.25} aria-hidden />
            <Text color="secondary">Enregistrez une séance avec le micro du Mac, ou importez un fichier.</Text>
            <Button variant="primary" label="Nouvelle séance" icon={<Plus size={16} strokeWidth={1.75} />} onClick={onNewSession} />
          </div>
        </section>
      ) : (
        <>
          {ongoing.length > 0 && (
            <section className="cl-home__recent">
              <Heading level={2}>En cours</Heading>
              <SessionList sessions={ongoing} projectName={projectName} recordingId={recording?.session_id ?? null} />
            </section>
          )}
          {groups.map(([label, list]) => (
            <section key={label} className="cl-home__recent">
              <Heading level={2}>{label}</Heading>
              <SessionList sessions={list} projectName={projectName} recordingId={recording?.session_id ?? null} />
            </section>
          ))}
        </>
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
