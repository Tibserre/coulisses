import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { AudioLines, FileAudio, Upload } from "lucide-react";
import { api, type AppInfo, type Session } from "../api.ts";
import { JobBadge } from "../components/JobBadge.tsx";
import { AppFooter } from "../components/AppFooter.tsx";
import { formatBytes, formatDate, formatDuration, plural } from "../format.ts";

const ACCEPT =
  "audio/*,video/*,.wav,.m4a,.mp3,.flac,.ogg,.opus,.aac,.aif,.aiff,.caf,.mp4,.mov,.mkv,.webm";

export function LibraryPage() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [list, about] = await Promise.all([api.sessions(), api.info()]);
      setSessions(list);
      setInfo(about);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return (
    <div className="cl-page">
      <header className="cl-page__header">
        <Stack direction="horizontal" gap={2} vAlign="center">
          <AudioLines
            size={22}
            strokeWidth={1.75}
            color="var(--color-accent)"
            aria-hidden
          />
          <Heading level={1}>Coulisses</Heading>
        </Stack>
      </header>
      <main className="cl-library">
        <Stack gap={6}>
          {error && (
            <Banner
              status="error"
              title="Le service ne répond pas"
              description={error}
            />
          )}
          {info?.processing_error && (
            <Banner
              status="error"
              title="Le traitement en tâche de fond a rencontré une erreur"
              description={`${info.processing_error}. Il réessaie toutes les deux secondes ; si le message reste, relancez Coulisses.`}
            />
          )}
          {info && info.recovery_problems.length > 0 && (
            <Banner
              status="warning"
              title="À vérifier depuis le dernier lancement"
              collapsible={false}
            >
              <ul className="cl-list">
                {info.recovery_problems.map((p) => (
                  <li key={p}>
                    <Text>{p}</Text>
                  </li>
                ))}
              </ul>
            </Banner>
          )}
          <ImportPanel
            onImported={(id) => (window.location.hash = `#/seance/${id}`)}
          />
          <section>
            <Heading level={2}>Enregistrements</Heading>
            {sessions === null ? null : sessions.length === 0 ? (
              <div className="cl-empty">
                <FileAudio size={40} strokeWidth={1.25} aria-hidden />
                <Text color="secondary">
                  Aucun enregistrement pour l'instant. Importez un fichier pour
                  commencer.
                </Text>
              </div>
            ) : (
              <ul className="cl-sessions">
                {sessions.map((s) => (
                  <li key={s.id}>
                    <a
                      className="cl-sessions__item"
                      href={`#/seance/${encodeURIComponent(s.id)}`}
                    >
                      <span className="cl-sessions__title">
                        {s.title ??
                          `Séance du ${formatDate(s.recorded_at).toLowerCase()}`}
                      </span>
                      <Text color="secondary">
                        {formatDuration(s.duration_s)}
                        {s.attendee_count
                          ? ` · ${plural(s.attendee_count, "présent", "présents")}`
                          : ""}
                      </Text>
                      <JobBadge state={s.job_state} />
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </Stack>
      </main>
      <AppFooter info={info} />
    </div>
  );
}

function ImportPanel({ onImported }: { onImported: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [attendees, setAttendees] = useState<number | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const start = async () => {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const { id } = await api.importRecording(file, attendees, setProgress);
      onImported(id);
    } catch (e) {
      setError((e as Error).message);
      setProgress(null);
    }
  };

  return (
    <section
      className="cl-import"
      data-dragging={dragging || undefined}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const dropped = e.dataTransfer.files[0];
        if (dropped) setFile(dropped);
      }}
    >
      <Stack gap={4}>
        <Stack gap={1}>
          <Heading level={2}>Importer un enregistrement</Heading>
          <Text color="secondary">
            Un fichier audio ou vidéo, enregistré sur le Mac, un téléphone ou un
            enregistreur. Il est gardé tel quel ; le traitement démarre tout
            seul, en tâche de fond.
          </Text>
        </Stack>
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Stack direction="horizontal" gap={4} vAlign="end" wrap="wrap">
          <Stack gap={1}>
            <Button
              label={file ? "Choisir un autre fichier" : "Choisir un fichier"}
              icon={<Upload size={16} strokeWidth={1.75} />}
              onClick={() => input.current?.click()}
              isDisabled={progress !== null}
            />
            <Text type="supporting">
              {file
                ? `${file.name} · ${formatBytes(file.size)}`
                : "ou glissez-le ici"}
            </Text>
          </Stack>
          <div style={{ width: 200 }}>
            <NumberInput
              label="Nombre de présents"
              description="Au moins autant de voix seront cherchées."
              value={attendees}
              onChange={(v) =>
                setAttendees(
                  Number.isFinite(v) && v >= 1 ? Math.round(v) : null,
                )
              }
              isOptional
              isDisabled={progress !== null}
            />
          </div>
          <Button
            label="Importer et traiter"
            variant="primary"
            onClick={() => void start()}
            isDisabled={!file || progress !== null}
          />
        </Stack>
        {progress !== null && (
          <ProgressBar
            label="Envoi du fichier"
            value={progress * 100}
            hasValueLabel
          />
        )}
        {error && (
          <Banner status="error" title="Import refusé" description={error} />
        )}
      </Stack>
    </section>
  );
}
