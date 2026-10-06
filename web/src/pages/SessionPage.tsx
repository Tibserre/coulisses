import { useCallback, useEffect, useMemo, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { Popover } from "@astryxdesign/core/Popover";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { ArrowLeft } from "lucide-react";
import {
  api,
  type EditRequest,
  type CorrectedView,
  type Person,
  type SessionDetail,
  type StageView,
} from "../api.ts";
import { PlayerBar } from "../components/PlayerBar.tsx";
import { ProvenanceDialog } from "../components/ProvenanceDialog.tsx";
import { CorrectionsHistory, KeyFigures, Participants, Attendees } from "../components/ReviewSide.tsx";
import { StageList } from "../components/StageList.tsx";
import { GiveToPanel, TranscriptView, type Editing } from "../components/TranscriptView.tsx";
import { SummaryPanel } from "../components/SummaryPanel.tsx";
import { EditableTitle } from "../components/EditableTitle.tsx";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { formatBytes, formatDate, formatDuration, plural } from "../format.ts";
import { buildModel, liveEditsKey, toggleSelection, turnAt, wordAt } from "../transcript.ts";
import { usePlayback } from "../usePlayback.ts";
import { useDevMode } from "../devMode.ts";
import { describeStageError } from "../errors.ts";

/** Keys typed into a text field keep their meaning; on a button or a checkbox, N and E
 *  still work. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable || target.tagName === "TEXTAREA" || target.tagName === "SELECT") return true;
  if (target instanceof HTMLInputElement) return !["checkbox", "radio", "range", "button"].includes(target.type);
  return false;
}

export function SessionPage({ id }: { id: string }) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [view, setView] = useState<CorrectedView | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [provenanceOf, setProvenanceOf] = useState<StageView | null>(null);
  const [editingTurn, setEditingTurn] = useState<number | null>(null);
  const [namingTurn, setNamingTurn] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [lastSelected, setLastSelected] = useState<number | null>(null);
  const [giving, setGiving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<"overview" | "summary">("summary");
  const pb = usePlayback();
  const dev = useDevMode();

  const refresh = useCallback(async () => {
    try {
      setDetail(await api.session(id));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  const jobState = detail?.session.job_state;
  const spaceId = detail?.session.space_id;
  const attribute = detail?.stages.find((s) => s.stage === "attribute");
  const attributeRun = attribute?.state === "succeeded" ? attribute.run_id : null;

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Follow the processing while it runs; nothing to poll once it is over.
  useEffect(() => {
    if (jobState !== "queued" && jobState !== "running") return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [jobState, refresh]);

  useEffect(() => {
    if (!attributeRun) return;
    api.transcript(id).then(
      (t) => {
        setView(t);
        setTranscriptError(null);
      },
      (e: Error) => setTranscriptError(e.message),
    );
  }, [id, attributeRun]);

  const loadPeople = useCallback(async () => {
    if (spaceId != null) setPeople(await api.people(spaceId));
  }, [spaceId]);
  useEffect(() => {
    void loadPeople().catch((e: Error) => setError(e.message));
  }, [loadPeople]);

  const model = useMemo(() => (view ? buildModel(view) : null), [view]);
  const currentRow = model ? turnAt(model, pb.time) : null;
  const current = currentRow ? { row: currentRow, word: wordAt(currentRow, pb.time) } : null;

  const correct = useCallback(
    async (correction: EditRequest) => {
      try {
        setView(await api.addEdit(id, correction));
        setEditError(null);
      } catch (e) {
        setEditError((e as Error).message);
        throw e;
      }
    },
    [id],
  );

  const editing: Editing = useMemo(
    () => ({
      people,
      correct,
      addGuest: async (name: string) => {
        const guest = await api.addPerson(spaceId!, { name, kind: "guest" });
        await loadPeople();
        return guest;
      },
      resetText: async (turn: number) => {
        try {
          setView(await api.resetText(id, turn));
          setEditError(null);
        } catch (e) {
          setEditError((e as Error).message);
          throw e;
        }
      },
      editingTurn,
      setEditingTurn,
      namingTurn,
      setNamingTurn,
      selected,
      toggleSelected: (turn: number, extend: boolean) => {
        const order = model ? model.rows.flatMap((r) => (r.kind === "turn" ? [r.turn.index] : [])) : [];
        setSelected((before) => toggleSelection(before, order, turn, extend ? lastSelected : null));
        setLastSelected(turn);
      },
    }),
    [people, correct, spaceId, loadPeople, id, editingTurn, namingTurn, selected, lastSelected, model],
  );

  /** Cmd-Z undoes the last correction still in force; Cmd-Shift-Z redoes the last one
   *  undone. Both go through the journal: nothing is erased (P5). */
  const history = useCallback(
    async (redo: boolean) => {
      const edits = view?.edits ?? [];
      try {
        if (redo) {
          const target = edits
            .filter((e) => e.reverted && !e.redone && e.undone_by != null)
            .sort((a, b) => (b.undone_by ?? 0) - (a.undone_by ?? 0))[0];
          if (!target) return setNotice("Rien à rétablir.");
          setView(await api.redo(id, target.id));
          setNotice(`Rétabli : ${target.description}`);
        } else {
          const target = edits.filter((e) => !e.reverted).sort((a, b) => b.id - a.id)[0];
          if (!target) return setNotice("Rien à annuler.");
          setView(await api.undo(id, target.id));
          setNotice(`Annulé : ${target.description}`);
        }
        setEditError(null);
      } catch (e) {
        setEditError((e as Error).message);
      }
    },
    [id, view],
  );

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // N names the voice of the line being heard, E puts the cursor in its text; Cmd-Z and
  // Cmd-Shift-Z undo and redo corrections (inside a line being typed into, they undo the
  // typing, as anywhere).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      if ((e.metaKey || e.ctrlKey) && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        void history(e.shiftKey);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || !currentRow) return;
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        setNamingTurn(currentRow.turn.index);
      } else if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        setEditingTurn(currentRow.turn.index);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [currentRow, history]);

  const session = detail?.session;
  const title = session ? (session.title ?? `Séance du ${formatDate(session.recorded_at).toLowerCase()}`) : "";
  const present = session ? session.attendee_ids.length + (session.unnamed_attendees ?? 0) : 0;

  return (
    <div className="cl-review">
      <audio ref={pb.audioRef} src={api.audioUrl(id)} preload="metadata" />
      <header className="cl-review__header">
        <a className="cl-back" href="#/">
          <ArrowLeft size={16} strokeWidth={1.75} aria-hidden /> Enregistrements
        </a>
        {session && (
          <div>
            <Text type="supporting">
              {session.space_name} · {detail?.source?.origin === "captured" ? "enregistrement capté" : "enregistrement importé"}
            </Text>
            <EditableTitle
              title={title}
              onSave={async (value) => {
                await api.renameSession(id, value);
                await refresh();
              }}
            />
            <Text color="secondary">
              {formatDate(session.recorded_at)} · {formatDuration(session.duration_s)}
              {present ? ` · ${plural(present, "présent", "présents")}` : ""}
            </Text>
          </div>
        )}
      </header>

      {error && (
        <div className="cl-review__notice">
          <Banner status="error" title="Séance illisible" description={error} />
        </div>
      )}
      {detail && !model && (
        <ProcessingPanel
          detail={detail}
          transcriptError={transcriptError}
          onResume={async (attendees) => {
            await api.resume(id, attendees);
            await refresh();
          }}
          onShowProvenance={setProvenanceOf}
        />
      )}
      {detail && model && view && session && (
        <>
          <div className="cl-review__columns">
            <div className="cl-review__main">
              {editError && (
                <div className="cl-review__notice">
                  <Banner
                    status="error"
                    title="EditRequest refusée"
                    description={editError}
                    isDismissable
                    onDismiss={() => setEditError(null)}
                  />
                </div>
              )}
              {view.other_run_edits > 0 && (
                <div className="cl-review__notice">
                  <Banner
                    status="warning"
                    title={`${plural(view.other_run_edits, "correction faite", "corrections faites")} sur un traitement précédent`}
                    description="Elles sont gardées, mais pas encore reportées sur ce traitement."
                  />
                </div>
              )}
              <TranscriptView model={model} pb={pb} current={current} editing={editing} />
              {notice && (
                <div className="cl-notice" role="status">
                  {notice}
                </div>
              )}
              {selected.size > 0 && (
                <div className="cl-selection" role="toolbar" aria-label="Répliques sélectionnées">
                  <Text>{plural(selected.size, "réplique sélectionnée", "répliques sélectionnées")}</Text>
                  <Popover
                    isOpen={giving}
                    onOpenChange={setGiving}
                    label="Donner les répliques à"
                    width={280}
                    content={
                      <GiveToPanel
                        voices={model.speakers}
                        except={null}
                        onGive={(target) => {
                          setGiving(false);
                          void correct({ kind: "reassign_turns", turns: [...selected], target }).then(
                            () => setSelected(new Set()),
                            () => undefined,
                          );
                        }}
                      />
                    }
                  >
                    <Button size="sm" variant="primary" label="Donner à…" />
                  </Popover>
                  <Button size="sm" variant="ghost" label="Désélectionner" onClick={() => setSelected(new Set())} />
                </div>
              )}
            </div>
            <aside className="cl-side">
              <TabList value={tab} onChange={(v) => setTab(v as "overview" | "summary")} hasDivider>
                <Tab value="overview" label="Vue d'ensemble" />
                <Tab value="summary" label="Résumé" />
              </TabList>
              {tab === "summary" ? (
                <SummaryPanel
                  sessionId={id}
                  spaceId={session.space_id}
                  transcriptKey={liveEditsKey(view)}
                />
              ) : (
                <>
              <KeyFigures view={view} model={model} duration={session.duration_s} dev={dev} />
              <Participants model={model} />
              <Attendees
                session={session}
                people={people}
                onSave={async (ids, unnamed) => {
                  await api.setAttendees(id, ids, unnamed);
                  await refresh();
                }}
              />
              <CorrectionsHistory
                edits={view.edits}
                onUndo={async (editId) => setView(await api.undo(id, editId))}
                onRedo={async (editId) => setView(await api.redo(id, editId))}
              />
              {(dev || detail.stages.some((s) => s.state === "failed" || s.state === "stalled" || s.folder_missing)) && (
                <section>
                  <Heading level={3}>Traitement</Heading>
                  <StageList stages={detail.stages} onShowProvenance={setProvenanceOf} />
                </section>
              )}
              {dev && <SourceInfo detail={detail} />}
                </>
              )}
            </aside>
          </div>
          <PlayerBar model={model} pb={pb} current={currentRow} />
        </>
      )}
      <ProvenanceDialog sessionId={id} stage={provenanceOf} onClose={() => setProvenanceOf(null)} />
    </div>
  );
}

function ProcessingPanel({
  detail,
  transcriptError,
  onResume,
  onShowProvenance,
}: {
  detail: SessionDetail;
  transcriptError: string | null;
  onResume: (attendees?: number) => Promise<void>;
  onShowProvenance: (s: StageView) => void;
}) {
  const { session } = detail;
  const dev = useDevMode();
  const failed = session.job_state === "failed";
  const failedStage = detail.stages.find((s) => s.state === "failed");
  const failure = dev
    ? `${session.job_error ?? "Erreur inconnue"}.`
    : failedStage
      ? `« ${failedStage.label} » : ${describeStageError(failedStage) ?? "échec"}`
      : (session.job_error ?? "Erreur inconnue");
  const running = session.job_state === "queued" || session.job_state === "running";
  const attributed = detail.stages.some((s) => s.stage === "attribute" && s.state === "succeeded");
  const tooFew = failedStage?.error_code === "too_few_speakers";
  const found = Number(failedStage?.error_details?.found);
  const [attendees, setAttendees] = useState<number | null>(null);
  const proposed = attendees ?? (Number.isFinite(found) && found >= 1 ? found : 1);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const resume = async (withAttendees?: number) => {
    setResumeError(null);
    try {
      await onResume(withAttendees);
    } catch (e) {
      setResumeError((e as Error).message);
    }
  };
  return (
    <main className="cl-processing">
      <Heading level={2}>
        {failed
          ? "Le traitement s'est arrêté"
          : session.job_state === "done"
            ? "Traitement terminé"
            : running
              ? "Traitement en cours"
              : "Jamais traitée"}
      </Heading>
      {session.job_state === null && (
        <Banner
          status="warning"
          title="Aucun traitement n'a été demandé pour cet enregistrement"
          description="Cela ne devrait pas arriver après un import : signalez-le."
        />
      )}
      {running && (
        <Text color="secondary">
          Environ 10 minutes de calcul par heure d'audio. Vous pouvez fermer
          cette page : le traitement continue tant que Coulisses tourne, et
          reprend où il en était s'il est interrompu.
        </Text>
      )}
      {session.job_state === "queued" && (
        <Text color="secondary">
          En file : un autre enregistrement est peut-être en cours de
          traitement.
        </Text>
      )}
      {failed && (
        <Banner
          status="error"
          title="Une étape a échoué"
          description={`${failure} Les étapes réussies sont gardées ; reprendre ne relance que le reste.`}
          endContent={
            tooFew ? undefined : (
              <Button
                label="Reprendre le traitement"
                variant="primary"
                size="sm"
                clickAction={() => resume()}
              />
            )
          }
        />
      )}
      {failed && tooFew && (
        <div className="cl-retry">
          <div style={{ width: 200 }}>
            <NumberInput
              label="Nombre de présents"
              description="Au moins autant de voix seront cherchées."
              value={proposed}
              onChange={(v) => setAttendees(Number.isFinite(v) && v >= 1 ? Math.round(v) : null)}
            />
          </div>
          <Button
            label={`Reprendre avec ${proposed} présent${proposed > 1 ? "s" : ""}`}
            variant="primary"
            clickAction={() => resume(proposed)}
          />
        </div>
      )}
      {resumeError && (
        <Banner status="error" title="La reprise a échoué" description={resumeError} />
      )}
      {detail.source && !detail.source.file_present && (
        <Banner
          status="error"
          title="Enregistrement introuvable"
          description={`Le fichier ${detail.source.file_name} n'est plus dans le dossier de la séance. A-t-il été déplacé ou supprimé dans le Finder ?`}
        />
      )}
      {transcriptError && (
        <Banner
          status="error"
          title="Transcript illisible"
          description={transcriptError}
        />
      )}
      <StageList stages={detail.stages} onShowProvenance={onShowProvenance} />
      {session.job_state === "done" && attributed && !transcriptError && (
        <Spinner label="Chargement du transcript" />
      )}
      {session.job_state === "done" && !attributed && (
        <Banner
          status="error"
          title="Traitement terminé, mais le transcript est absent"
          description="L'étape « Qui a dit quoi » n'a pas de résultat réussi. Consultez les étapes ci-dessus."
        />
      )}
    </main>
  );
}

function SourceInfo({ detail }: { detail: SessionDetail }) {
  const source = detail.source;
  if (!source) return null;
  return (
    <section>
      <Heading level={3}>Enregistrement</Heading>
      <MetadataList label={{ position: "start", width: 110 }}>
        <MetadataListItem label="Fichier d'origine">
          {source.original_name}
        </MetadataListItem>
        <MetadataListItem label="Taille">
          {formatBytes(source.size_bytes)}
        </MetadataListItem>
        <MetadataListItem label="Format">
          {[
            source.codec,
            source.sample_rate ? `${source.sample_rate / 1000} kHz` : null,
            source.channels ? plural(source.channels, "canal", "canaux") : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </MetadataListItem>
        <MetadataListItem label="Empreinte">
          <code className="cl-code" title={source.sha256}>
            {source.sha256.slice(0, 16)}…
          </code>
        </MetadataListItem>
      </MetadataList>
    </section>
  );
}
