import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Heading } from "@astryxdesign/core/Heading";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { FileAudio, Upload } from "lucide-react";
import {
  api,
  type AppInfo,
  type Person,
  type Session,
  type Space,
} from "../api.ts";
import { AppFooter } from "../components/AppFooter.tsx";
import { AppHeader } from "../components/AppHeader.tsx";
import { JobBadge } from "../components/JobBadge.tsx";
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

  const spaceCount = new Set(sessions?.map((s) => s.space_id)).size;

  return (
    <div className="cl-page">
      <AppHeader current="library" />
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
                {sessions.map((s) => {
                  const present =
                    s.attendee_ids.length + (s.unnamed_attendees ?? 0);
                  return (
                    <li key={s.id}>
                      <a
                        className="cl-sessions__item"
                        href={`#/seance/${encodeURIComponent(s.id)}`}
                      >
                        <span>
                          <span className="cl-sessions__title">
                            {s.title ??
                              `Séance du ${formatDate(s.recorded_at).toLowerCase()}`}
                          </span>
                          {spaceCount > 1 && (
                            <Text type="supporting"> · {s.space_name}</Text>
                          )}
                        </span>
                        <Text color="secondary">
                          {formatDuration(s.duration_s)}
                          {present
                            ? ` · ${plural(present, "présent", "présents")}`
                            : ""}
                        </Text>
                        <JobBadge state={s.job_state} />
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </Stack>
      </main>
      <AppFooter info={info} />
    </div>
  );
}

/** Who was there: people of the space to check, guests to add, and a number of people
 *  nobody will name. Their total is the minimum of voices (P3). */
function AttendeesPicker({
  space,
  personIds,
  setPersonIds,
  unnamed,
  setUnnamed,
  disabled,
}: {
  space: Space;
  personIds: number[];
  setPersonIds: (ids: number[]) => void;
  unnamed: number | null;
  setUnnamed: (n: number | null) => void;
  disabled: boolean;
}) {
  const [people, setPeople] = useState<Person[]>([]);
  const [guest, setGuest] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.people(space.id).then(
      (list) => setPeople(list.filter((p) => !p.archived)),
      (e: Error) => setError(e.message),
    );
  }, [space.id]);
  const total = personIds.length + (unnamed ?? 0);
  const addGuest = async () => {
    if (!guest.trim()) return;
    try {
      const person = await api.addPerson(space.id, {
        name: guest.trim(),
        kind: "guest",
      });
      setPeople((before) => [...before, person]);
      setPersonIds([...personIds, person.id]);
      setGuest("");
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Stack gap={3}>
      <Text weight="medium">Présents</Text>
      {people.length === 0 ? (
        <Text type="supporting">
          Personne dans cet espace pour l'instant. Ajoutez des membres depuis la
          page Espaces, ou un invité ci-dessous.
        </Text>
      ) : (
        <div className="cl-checklist cl-checklist--columns">
          {people.map((p) => (
            <CheckboxInput
              key={p.id}
              label={p.name}
              description={
                p.kind === "guest" ? "invité" : (p.role ?? undefined)
              }
              value={personIds.includes(p.id)}
              isDisabled={disabled}
              onChange={(checked) =>
                setPersonIds(
                  checked
                    ? [...personIds, p.id]
                    : personIds.filter((x) => x !== p.id),
                )
              }
            />
          ))}
        </div>
      )}
      <Stack direction="horizontal" gap={4} vAlign="end" wrap="wrap">
        <div style={{ width: 240 }}>
          <TextInput
            label="Ajouter un invité"
            value={guest}
            onChange={setGuest}
            onEnter={() => void addGuest()}
            isDisabled={disabled}
          />
        </div>
        <Button
          label="Ajouter"
          onClick={() => void addGuest()}
          isDisabled={disabled || !guest.trim()}
        />
        <div style={{ width: 200 }}>
          <NumberInput
            label="Présents non nommés"
            value={unnamed}
            onChange={(v) =>
              setUnnamed(Number.isFinite(v) && v >= 1 ? Math.round(v) : null)
            }
            isOptional
            isDisabled={disabled}
          />
        </div>
      </Stack>
      <Text type="supporting">
        {total
          ? `Au moins ${plural(total, "voix sera cherchée", "voix seront cherchées")}.`
          : "Sans présents, le moteur décide seul du nombre de voix."}
      </Text>
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
    </Stack>
  );
}

function ImportPanel({ onImported }: { onImported: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState<number | null>(null);
  const [personIds, setPersonIds] = useState<number[]>([]);
  const [unnamed, setUnnamed] = useState<number | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    api.spaces().then(
      (list) => {
        const open = list.filter((s) => !s.archived);
        setSpaces(open);
        setSpaceId((current) => current ?? open[0]?.id ?? null);
      },
      (e: Error) => setError(e.message),
    );
  }, []);
  const space = spaces.find((s) => s.id === spaceId) ?? null;

  const start = async () => {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const { id } = await api.importRecording(
        file,
        { spaceId, personIds, unnamed },
        setProgress,
      );
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
      <Stack gap={5}>
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
          {spaces.length > 1 && (
            <label className="cl-select">
              <span>Espace</span>
              <select
                value={spaceId ?? ""}
                disabled={progress !== null}
                onChange={(e) => {
                  setSpaceId(Number(e.target.value));
                  setPersonIds([]);
                }}
              >
                {spaces.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </Stack>
        {space && (
          <AttendeesPicker
            space={space}
            personIds={personIds}
            setPersonIds={setPersonIds}
            unnamed={unnamed}
            setUnnamed={setUnnamed}
            disabled={progress !== null}
          />
        )}
        <div>
          <Button
            label="Importer et traiter"
            variant="primary"
            onClick={() => void start()}
            isDisabled={!file || progress !== null}
          />
        </div>
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
