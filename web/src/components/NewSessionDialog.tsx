import { useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { IconButton } from "@astryxdesign/core/IconButton";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Stack } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Mic, MonitorSpeaker, Plus, Upload, X } from "lucide-react";
import { api, type InputDevice, type Person, type Project, type Space } from "../api.ts";
import { formatBytes, plural } from "../format.ts";

/** What was chosen last time, offered again (this browser only). */
const WHERE_KEY = "coulisses.nouvelle-seance.lieu";
type Where = "sur-place" | "en-ligne";
export type Way = "enregistrer" | "importer";

function remembered(): Where {
  try {
    return localStorage.getItem(WHERE_KEY) === "en-ligne" ? "en-ligne" : "sur-place";
  } catch {
    return "sur-place";
  }
}

function remember(where: Where): void {
  try {
    localStorage.setItem(WHERE_KEY, where);
  } catch {
    // Not remembered: offered as « sur place » next time, nothing else lost.
  }
}

const ACCEPT =
  "audio/*,video/*,.wav,.m4a,.mp3,.flac,.ogg,.opus,.aac,.aif,.aiff,.caf,.mp4,.mov,.mkv,.webm";

/** « Nouvelle note », opened by « ou importer un fichier » (ADR 0056): import a file, or record
 *  with everything chosen first. First how: record now, or import a file
 *  recorded elsewhere. Then where it goes (space, project) and who is there. To record:
 *  where the session is held (in the room, or online: the computer's sound too) and the
 *  microphones, as many as wanted (« Ajouter un micro »). The sound is kept as it is; the
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
  /** Where it was asked from (a space's « + », the session shown), and how (the home
   *  page's « importer un fichier »). */
  initial: { spaceId: number | null; projectId: number | null; way?: Way };
  /** A recording is in progress: another cannot start. */
  recording: boolean;
  onImported: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const open = spaces.filter((s) => !s.archived);
  const [way, setWay] = useState<Way>("enregistrer");
  const [spaceId, setSpaceId] = useState<number | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [personIds, setPersonIds] = useState<number[]>([]);
  const [unnamed, setUnnamed] = useState<number | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [microphones, setMicrophones] = useState<InputDevice[] | null>(null);
  /** The microphones chosen, the main one first (the one processed). */
  const [chosen, setChosen] = useState<number[]>([]);
  const [where, setWhere] = useState<Where>(remembered);
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
    setWay(recording ? "importer" : (initial.way ?? "enregistrer"));
    api.microphones().then(
      (found) => {
        setMicrophones(found);
        const main = found.find((m) => m.default)?.index ?? found[0]?.index;
        setChosen(main === undefined ? [] : [main]);
      },
      (e: Error) => setError(e.message),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on opening only
  }, [isOpen]);

  const space = open.find((s) => s.id === spaceId) ?? null;
  const spaceProjects = projects.filter((p) => p.space_id === spaceId && !p.archived);
  const busy = progress !== null || starting;
  const free = (microphones ?? []).filter((m) => !chosen.includes(m.index));

  const record = async () => {
    setError(null);
    setStarting(true);
    try {
      await api.startRecording({
        espace: spaceId,
        projet: projectId,
        presents: personIds,
        non_nommes: unnamed,
        micro: chosen[0] ?? null,
        micros_en_plus: chosen.slice(1),
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
    <Dialog
      isOpen={isOpen}
      onOpenChange={(o) => !o && !busy && onClose()}
      width={640}
      maxHeight="min(88vh, 820px)"
    >
      <DialogHeader title="Nouvelle note" onOpenChange={() => !busy && onClose()} />
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
          if (busy) return; // a file being sent, or a recording starting: left as it is
          const dropped = e.dataTransfer.files[0];
          if (dropped) {
            setFile(dropped);
            setWay("importer");
          }
        }}
      >
        <div className="cl-newsession__body">
          <SegmentedControl
            label="Comment"
            value={way}
            onChange={(v: string) => setWay(v === "importer" ? "importer" : "enregistrer")}
            layout="fill"
            isDisabled={busy}
          >
            <SegmentedControlItem
              value="enregistrer"
              label="Enregistrer maintenant"
              icon={<Mic size={16} strokeWidth={1.75} />}
            />
            <SegmentedControlItem
              value="importer"
              label="Importer un fichier"
              icon={<Upload size={16} strokeWidth={1.75} />}
            />
          </SegmentedControl>

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

          {way === "enregistrer" ? (
            <section className="cl-newsession__section">
              <Text weight="medium">Où se passe la séance ?</Text>
              <SegmentedControl
                label="Où se passe la séance"
                value={where}
                onChange={(v: string) => {
                  const next: Where = v === "en-ligne" ? "en-ligne" : "sur-place";
                  setWhere(next);
                  remember(next);
                }}
                size="sm"
                layout="fill"
                isDisabled={busy}
              >
                <SegmentedControlItem value="sur-place" label="Sur place" />
                <SegmentedControlItem value="en-ligne" label="En ligne ou hybride" />
              </SegmentedControl>

              <Text weight="medium">Ce qui est enregistré</Text>
              <ul className="cl-sources" aria-label="Ce qui est enregistré">
                {chosen.map((index, k) => (
                  <li key={k} className="cl-sources__row">
                    <Mic size={16} strokeWidth={1.75} aria-hidden />
                    <select
                      aria-label={k === 0 ? "Micro principal" : `Micro ${k + 1}`}
                      value={index}
                      disabled={busy}
                      onChange={(e) => {
                        const next = [...chosen];
                        next[k] = Number(e.target.value);
                        setChosen(next);
                      }}
                    >
                      {(microphones ?? [])
                        .filter((m) => m.index === index || !chosen.includes(m.index))
                        .map((m) => (
                          <option key={m.index} value={m.index}>
                            {m.name}
                          </option>
                        ))}
                    </select>
                    {k === 0 ? (
                      <span className="cl-sources__note">principal</span>
                    ) : (
                      <IconButton
                        label="Retirer ce micro"
                        icon={<X size={14} strokeWidth={1.75} />}
                        variant="ghost"
                        size="sm"
                        onClick={() => setChosen(chosen.filter((_, j) => j !== k))}
                        isDisabled={busy}
                      />
                    )}
                  </li>
                ))}
                {where === "en-ligne" && (
                  <li className="cl-sources__row">
                    <MonitorSpeaker size={16} strokeWidth={1.75} aria-hidden />
                    <span className="cl-sources__fixed">Son de l'ordinateur</span>
                    <span className="cl-sources__note">réuni au micro principal</span>
                  </li>
                )}
              </ul>
              {microphones && microphones.length === 0 && (
                <Text type="supporting">Aucun micro trouvé : branchez-en un.</Text>
              )}
              {microphones && microphones.length > 0 && free.length === 0 && (
                <Text type="supporting">
                  Tous les micros du Mac sont dans la liste. Un iPhone proche et déverrouillé y
                  apparaît de lui-même : rouvrez ce dialogue s'il manque.
                </Text>
              )}
              <div>
                <Button
                  label="Ajouter un micro"
                  variant="ghost"
                  size="sm"
                  icon={<Plus size={14} strokeWidth={1.75} />}
                  onClick={() => free[0] && setChosen([...chosen, free[0].index])}
                  isDisabled={busy || free.length === 0}
                />
              </div>
              <Text type="supporting">
                {where === "en-ligne"
                  ? "On entend aussi les personnes à distance, même avec un casque. "
                  : ""}
                Un iPhone proche du Mac apparaît dans la liste des micros. Les micros ajoutés sont
                gardés à côté ; seul le principal est traité pour l'instant.
              </Text>
            </section>
          ) : (
            <section className="cl-newsession__section">
              <Text weight="medium">Le fichier</Text>
              <div className="cl-dropzone" data-dragging={dragging || undefined}>
                <Upload size={20} strokeWidth={1.75} aria-hidden />
                <Text>
                  {file ? `${file.name} · ${formatBytes(file.size)}` : "Glissez ici un fichier audio ou vidéo"}
                </Text>
                <Button
                  label={file ? "Un autre fichier" : "Choisir un fichier"}
                  size="sm"
                  onClick={() => input.current?.click()}
                  isDisabled={busy}
                />
                <input
                  ref={input}
                  type="file"
                  accept={ACCEPT}
                  hidden
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </div>
            </section>
          )}
        </div>

        <footer className="cl-newsession__footer">
          {progress !== null && <ProgressBar label="Envoi du fichier" value={progress * 100} hasValueLabel />}
          {error && <Banner status="error" title="Refusé" description={error} />}
          {way === "enregistrer" && recording && (
            <Text type="supporting">Un enregistrement est déjà en cours : arrêtez-le d'abord.</Text>
          )}
          <div className="cl-newsession__actions">
            <Button label="Annuler" variant="ghost" onClick={onClose} isDisabled={busy} />
            {way === "enregistrer" ? (
              <Button
                label="Commencer l'enregistrement"
                variant="primary"
                icon={<Mic size={16} strokeWidth={1.75} />}
                onClick={() => void record()}
                isDisabled={recording || busy || chosen.length === 0}
              />
            ) : (
              <Button
                label="Importer et traiter"
                variant="primary"
                icon={<Upload size={16} strokeWidth={1.75} />}
                onClick={() => void importFile()}
                isDisabled={busy || !file}
              />
            )}
          </div>
        </footer>
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
        <div style={{ width: 200 }}>
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
            label="Non nommés"
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

