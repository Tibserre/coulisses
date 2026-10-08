import { useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Mic, Upload } from "lucide-react";
import { api, type InputDevice, type Person, type Project, type Space } from "../api.ts";
import { formatBytes, plural } from "../format.ts";

/** Where the last session was held, offered again (this browser only). */
const WHERE_KEY = "coulisses.nouvelle-seance.lieu";
type Where = "sur-place" | "en-ligne";

function rememberedWhere(): Where {
  try {
    return localStorage.getItem(WHERE_KEY) === "en-ligne" ? "en-ligne" : "sur-place";
  } catch {
    return "sur-place";
  }
}

const ACCEPT =
  "audio/*,video/*,.wav,.m4a,.mp3,.flac,.ogg,.opus,.aac,.aif,.aiff,.caf,.mp4,.mov,.mkv,.webm";

/** « Nouvelle séance » (⌘N, or « + » on a space): where it goes (space, project), who is
 *  there, then record with the Mac's microphone (with the computer's sound, for a meeting
 *  online or hybrid) or import a file recorded elsewhere. The sound is kept as it is; the
 *  processing starts by itself, in the background. */
export function NewSessionDialog({
  isOpen,
  onClose,
  spaces,
  projects,
  initial,
  recording,
  onImported,
}: {
  isOpen: boolean;
  onClose: () => void;
  spaces: Space[];
  projects: Project[];
  /** Where it was asked from (a space's « + », the session shown). */
  initial: { spaceId: number | null; projectId: number | null };
  /** A recording is in progress: another cannot start. */
  recording: boolean;
  onImported: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const open = spaces.filter((s) => !s.archived);
  const [spaceId, setSpaceId] = useState<number | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [personIds, setPersonIds] = useState<number[]>([]);
  const [unnamed, setUnnamed] = useState<number | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [microphones, setMicrophones] = useState<InputDevice[] | null>(null);
  const [micro, setMicro] = useState<number | null>(null);
  const [micro2, setMicro2] = useState<number | null>(null);
  const [where, setWhere] = useState<Where>(rememberedWhere);
  const [starting, setStarting] = useState(false);

  // Each opening starts from where it was asked.
  useEffect(() => {
    if (!isOpen) return;
    const space = open.find((s) => s.id === initial.spaceId) ?? open[0] ?? null;
    setSpaceId(space?.id ?? null);
    setProjectId(space && space.id === initial.spaceId ? initial.projectId : null);
    setPersonIds([]);
    setUnnamed(null);
    setFile(null);
    setProgress(null);
    setError(null);
    setStarting(false);
    setMicro2(null);
    api.microphones().then(
      (found) => {
        setMicrophones(found);
        setMicro((current) => current ?? found.find((m) => m.default)?.index ?? found[0]?.index ?? null);
      },
      (e: Error) => setError(e.message),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on opening only
  }, [isOpen]);

  const space = open.find((s) => s.id === spaceId) ?? null;
  const spaceProjects = projects.filter((p) => p.space_id === spaceId && !p.archived);
  const busy = progress !== null || starting;

  const record = async () => {
    setError(null);
    setStarting(true);
    try {
      await api.startRecording({
        espace: spaceId,
        projet: projectId,
        presents: personIds,
        non_nommes: unnamed,
        micro,
        micro2,
        son_ordinateur: where === "en-ligne",
      });
      onClose();
      window.location.hash = "#/enregistrement";
    } catch (e) {
      setError((e as Error).message);
      setStarting(false);
    }
  };

  const importFile = async () => {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const { id } = await api.importRecording(file, { spaceId, projectId, personIds, unnamed }, setProgress);
      onClose();
      onImported(id);
    } catch (e) {
      setError((e as Error).message);
      setProgress(null);
    }
  };

  return (
    <Dialog isOpen={isOpen} onOpenChange={(o) => !o && !busy && onClose()} width={680}>
      <DialogHeader title="Nouvelle séance" onOpenChange={() => !busy && onClose()} />
      <div
        className="cl-newsession"
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
          <div className="cl-newsession__where">
            <label className="cl-select">
              <span>Espace</span>
              <select
                value={spaceId ?? ""}
                disabled={busy}
                onChange={(e) => {
                  setSpaceId(Number(e.target.value));
                  setProjectId(null);
                  setPersonIds([]);
                }}
              >
                {open.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="cl-select">
              <span>Projet</span>
              <select
                value={projectId ?? ""}
                disabled={busy}
                onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Aucun projet</option>
                {spaceProjects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {space && (
            <AttendeesPicker
              space={space}
              personIds={personIds}
              setPersonIds={setPersonIds}
              unnamed={unnamed}
              setUnnamed={setUnnamed}
              disabled={busy}
            />
          )}
          <div className="cl-newsession__ways">
            <section>
              <Text weight="medium">Enregistrer ici</Text>
              <SegmentedControl
                label="Où se passe la séance"
                value={where}
                onChange={(v: string) => {
                  const next: Where = v === "en-ligne" ? "en-ligne" : "sur-place";
                  setWhere(next);
                  try {
                    localStorage.setItem(WHERE_KEY, next);
                  } catch {
                    // Not remembered: offered as « sur place » next time, nothing else lost.
                  }
                }}
                size="sm"
                layout="fill"
                isDisabled={busy}
              >
                <SegmentedControlItem value="sur-place" label="Sur place" />
                <SegmentedControlItem value="en-ligne" label="En ligne ou hybride" />
              </SegmentedControl>
              <Text type="supporting">
                {where === "en-ligne"
                  ? "Le micro et le son de l'ordinateur, enregistrés ensemble : on entend aussi les personnes à distance."
                  : "Avec le micro ; l'écran d'enregistrement s'ouvre."}
              </Text>
              {microphones && microphones.length > 0 && (
                <label className="cl-select">
                  <span>Micro</span>
                  <select
                    value={micro ?? ""}
                    disabled={busy}
                    onChange={(e) => {
                      const next = Number(e.target.value);
                      setMicro(next);
                      if (micro2 === next) setMicro2(null);
                    }}
                  >
                    {microphones.map((m) => (
                      <option key={m.index} value={m.index}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {microphones && microphones.length > 1 && (
                <label className="cl-select">
                  <span>Deuxième micro, en même temps</span>
                  <select
                    value={micro2 ?? ""}
                    disabled={busy}
                    onChange={(e) => setMicro2(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Aucun</option>
                    {microphones
                      .filter((m) => m.index !== micro)
                      .map((m) => (
                        <option key={m.index} value={m.index}>
                          {m.name}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              {micro2 !== null && (
                <Text type="supporting">
                  Gardé comme une seconde piste ; seule la première est traitée pour l'instant.
                </Text>
              )}
              <div>
                <Button
                  label="Enregistrer"
                  variant="primary"
                  icon={<Mic size={16} strokeWidth={1.75} />}
                  onClick={() => void record()}
                  isDisabled={recording || busy || micro === null}
                />
              </div>
              {recording && (
                <Text type="supporting">Un enregistrement est déjà en cours : arrêtez-le d'abord.</Text>
              )}
            </section>
            <section>
              <Text weight="medium">Importer un fichier</Text>
              <Text type="supporting">
                {file ? `${file.name} · ${formatBytes(file.size)}` : "Audio ou vidéo enregistré ailleurs ; ou glissez-le ici."}
              </Text>
              <input
                ref={input}
                type="file"
                accept={ACCEPT}
                hidden
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <div className="cl-newsession__buttons">
                <Button
                  label={file ? "Un autre fichier" : "Choisir un fichier"}
                  icon={<Upload size={16} strokeWidth={1.75} />}
                  onClick={() => input.current?.click()}
                  isDisabled={busy}
                />
                {file && <Button label="Importer et traiter" onClick={() => void importFile()} isDisabled={busy} />}
              </div>
            </section>
          </div>
          {progress !== null && (
            <ProgressBar label="Envoi du fichier" value={progress * 100} hasValueLabel />
          )}
          {error && <Banner status="error" title="Refusé" description={error} />}
        </Stack>
      </div>
    </Dialog>
  );
}

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
          Personne dans cet espace pour l'instant. Ajoutez des membres dans les
          paramètres de l'espace, ou un invité ci-dessous.
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
        <div style={{ width: 240 }}>
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

