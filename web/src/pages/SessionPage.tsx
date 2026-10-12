import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { Popover } from "@astryxdesign/core/Popover";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import {
  api,
  ServiceError,
  type EditRequest,
  type CorrectedView,
  type Person,
  type PhasesStatus,
  type Project,
  type Session,
  type SessionDetail,
  type StageView,
} from "../api.ts";
import { PhaseStrip } from "../components/PhaseStrip.tsx";
import { PlayerBar } from "../components/PlayerBar.tsx";
import { ReviewSkeleton } from "../components/ReviewSkeleton.tsx";
import { ProvenanceDialog } from "../components/ProvenanceDialog.tsx";
import { CorrectionsHistory, KeyFigures, Participants, Attendees } from "../components/ReviewSide.tsx";
import { StageList } from "../components/StageList.tsx";
import { GiveToPanel, TranscriptView, type Editing } from "../components/TranscriptView.tsx";
import { SummaryPanel } from "../components/SummaryPanel.tsx";
import { NotesSection } from "../components/NotesSection.tsx";
import { VersionsSection } from "../components/VersionsSection.tsx";
import { SessionMenu } from "../components/SessionMenu.tsx";
import { audioLine } from "../retention.ts";
import { libraryChanged } from "../library.ts";
import { RERUN_NAME } from "../versions.ts";
import { extraTracks } from "../tracks.ts";
import { takeStopProblem } from "../stopNotice.ts";
import { EditableTitle } from "../components/EditableTitle.tsx";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { formatBytes, formatDate, formatDuration, plural } from "../format.ts";
import { buildModel, liveEditsKey, phaseOf, toggleSelection, turnAt, wordAt } from "../transcript.ts";
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

export function SessionPage({
  id,
  at = null,
  tab: initialTab = null,
  projects = [],
}: {
  id: string;
  /** A measured time to open at (a search hit). */
  at?: number | null;
  tab?: "summary" | null;
  projects?: Project[];
}) {
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
  const [menuError, setMenuError] = useState<string | null>(null);
  const [stopProblem, setStopProblem] = useState<string | null>(null);
  // Said by the stop of the recording that just opened this page (P8).
  useEffect(() => setStopProblem(takeStopProblem(id)), [id]);
  const [incomplete, setIncomplete] = useState<string | null>(null);
  const [tab, setTab] = useState<"overview" | "summary">("summary");
  // Opened from a search hit in a summary: the summary tab.
  useEffect(() => {
    if (initialTab === "summary") setTab("summary");
  }, [initialTab]);
  /** Chapters folded by the user, by their first line. */
  const [folded, setFolded] = useState<Set<number>>(new Set());
  const [phasesStatus, setPhasesStatus] = useState<PhasesStatus | null>(null);
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
  // The version shown: it changes when a rerun completes, or when another one is shown.
  const attributeRun = detail?.version ?? null;
  const busy = jobState === "queued" || jobState === "running";

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Follow the processing while it runs; nothing to poll once it is over.
  useEffect(() => {
    if (jobState !== "queued" && jobState !== "running") return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [jobState, refresh]);

  // The version on screen. A new one (a rerun completed, another shown) is read once no
  // line is being typed into: never pulled from under the cursor. A correction typed for
  // the former one is refused by the service, and its text given back (`refused`).
  const viewRun = view?.run_id ?? null;
  const [typing, setTyping] = useState(false);
  useEffect(() => {
    if (!attributeRun || typing || viewRun === attributeRun) return;
    api.transcript(id).then(
      (t) => {
        setView(t);
        setTranscriptError(null);
      },
      (e: Error) => setTranscriptError(e.message),
    );
  }, [id, attributeRun, typing, viewRun]);

  // Another version has other lines: what pointed at them no longer does.
  const shownRun = useRef<string | null>(null);
  useEffect(() => {
    if (shownRun.current !== null && shownRun.current !== viewRun) {
      setFolded(new Set());
      setSelected(new Set());
      setNamingTurn(null);
    }
    shownRun.current = viewRun;
  }, [viewRun]);

  // The chapters: detected after the processing (or asked again), followed while they are.
  const loadPhases = useCallback(async () => {
    try {
      setPhasesStatus(await api.phases(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => {
    if (attributeRun) void loadPhases();
  }, [attributeRun, loadPhases]);
  const phasesWaiting = phasesStatus?.state === "queued" || phasesStatus?.state === "running";
  useEffect(() => {
    if (!phasesWaiting) return;
    const timer = window.setInterval(() => void loadPhases(), 3000);
    return () => {
      window.clearInterval(timer);
      // Over: the transcript gets its chapters.
      api.transcript(id).then(setView, (e: Error) => setTranscriptError(e.message));
    };
  }, [phasesWaiting, loadPhases, id]);

  // The title is proposed on demand, from the chapters (ADR 0026): asked, then followed
  // until it is there. A failure says why, next to the title.
  const [titleState, setTitleState] = useState<"waiting" | string | null>(null);
  const titleBefore = useRef<string | null>(null);
  const askTitle = () => {
    titleBefore.current = detail?.session.title ?? null;
    setTitleState("waiting");
    api.requestGeneration(id, "titre", null).catch((e: Error) => setTitleState(e.message));
  };
  useEffect(() => {
    if (titleState !== "waiting") return;
    const timer = window.setInterval(() => {
      api.generations(id).then(
        (g) => {
          const job = g.pending.find((p) => p.action_ref === "titre");
          if (job?.state === "failed") setTitleState(`Pas de titre proposé : ${job.error ?? "erreur inconnue"}`);
          else if (!job) {
            api.session(id).then(
              (d) => {
                setDetail(d);
                // « Séance sans contenu » is never written as a title: said, not silent.
                setTitleState(
                  d.session.title === titleBefore.current
                    ? "Pas de nouveau titre : le modèle n'a rien trouvé de substantiel, ou a proposé le même."
                    : null,
                );
              },
              (e: Error) => setTitleState(e.message),
            );
          }
        },
        (e: Error) => setTitleState(e.message),
      );
    }, 2000);
    return () => window.clearInterval(timer);
  }, [titleState, id]);

  const loadPeople = useCallback(async () => {
    if (spaceId != null) setPeople(await api.people(spaceId));
  }, [spaceId]);
  useEffect(() => {
    void loadPeople().catch((e: Error) => setError(e.message));
  }, [loadPeople]);

  // During playback, the chapter being heard stays open, even folded (art direction).
  const unfolded = useMemo(() => (view ? buildModel(view) : null), [view]);
  const heard = unfolded && pb.playing ? turnAt(unfolded, pb.time) : null;
  const heardChapter = view && heard ? phaseOf(view.phases, heard.turn.index)?.turn ?? null : null;
  const model = useMemo(() => {
    if (!view) return null;
    const shut = new Set([...folded].filter((t) => t !== heardChapter));
    return shut.size ? buildModel(view, shut) : unfolded;
  }, [view, folded, heardChapter, unfolded]);
  const currentRow = model ? turnAt(model, pb.time) : null;

  // Opened at a passage (a search hit): the player goes there, without playing, and the
  // line comes to the centre. Once the audio knows its length, so that the time holds.
  const sought = useRef<number | null>(null);
  useEffect(() => {
    if (at == null || !model || sought.current === at) return;
    const audio = pb.audioRef.current;
    const go = () => {
      sought.current = at;
      pb.seek(at, false);
    };
    if (!audio || audio.readyState >= 1) {
      go();
      return;
    }
    audio.addEventListener("loadedmetadata", go, { once: true });
    return () => audio.removeEventListener("loadedmetadata", go);
  }, [at, model, pb]);
  const current = currentRow ? { row: currentRow, word: wordAt(currentRow, pb.time) } : null;

  /** A correction refused. Meant for a version no longer shown (409): nothing was
   *  written; the page reads the version now shown, and a typed text is given back. */
  const refused = useCallback(
    (e: unknown, typed?: string) => {
      const error = e as Error;
      if (error instanceof ServiceError && error.status === 409) {
        setEditingTurn(null);
        setTyping(false);
        setEditError(`${error.message}${typed ? ` Votre texte, à reprendre : « ${typed} »` : ""}`);
        void refresh();
        return;
      }
      setEditError(error.message);
    },
    [refresh],
  );

  const correct = useCallback(
    async (correction: EditRequest) => {
      if (!viewRun) return;
      try {
        const next = await api.addEdit(id, correction, viewRun);
        setView(next);
        setEditError(null);
        // Naming a voice after a person who already has one merges them: said on screen.
        const last = next.edits.at(-1);
        if (correction.kind === "assign_speaker" && last?.kind === "merge_speakers")
          setNotice(`${last.description}. Cmd-Z pour annuler.`);
      } catch (e) {
        refused(
          e,
          correction.kind === "edit_text"
            ? correction.text
            : correction.kind === "set_phase"
              ? (correction.title ?? undefined)
              : undefined,
        );
        throw e;
      }
    },
    [id, viewRun, refused],
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
        if (!viewRun) return;
        try {
          setView(await api.resetText(id, turn, viewRun));
          setEditError(null);
        } catch (e) {
          refused(e);
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
      setTyping,
      toggleFolded: (turn: number) =>
        setFolded((before) => {
          const next = new Set(before);
          if (!next.delete(turn)) next.add(turn);
          return next;
        }),
    }),
    [people, correct, spaceId, loadPeople, id, editingTurn, namingTurn, selected, lastSelected, model, viewRun, refused],
  );

  /** Cmd-Z undoes the last correction still in force; Cmd-Shift-Z redoes the last one
   *  undone. Both go through the journal: nothing is erased (P5). */
  const history = useCallback(
    async (redo: boolean) => {
      const edits = view?.edits ?? [];
      if (!viewRun) return;
      try {
        if (redo) {
          const target = edits
            .filter((e) => e.reverted && !e.redone && e.undone_by != null)
            .sort((a, b) => (b.undone_by ?? 0) - (a.undone_by ?? 0))[0];
          if (!target) return setNotice("Rien à rétablir.");
          setView(await api.redo(id, target.id, viewRun));
          setNotice(`Rétabli : ${target.description}`);
        } else {
          const target = edits.filter((e) => !e.reverted).sort((a, b) => b.id - a.id)[0];
          if (!target) return setNotice("Rien à annuler.");
          setView(await api.undo(id, target.id, viewRun));
          setNotice(`Annulé : ${target.description}`);
        }
        setEditError(null);
      } catch (e) {
        refused(e);
      }
    },
    [id, view, viewRun, refused],
  );

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // N names the voice of the line being heard, E puts the cursor in its text, C starts a
  // chapter there; Cmd-Z and
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
      } else if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        void correct({ kind: "set_phase", turn: currentRow.turn.index }).catch(() => undefined);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [currentRow, history, correct]);

  const session = detail?.session;
  const title = session ? (session.title ?? `Séance du ${formatDate(session.recorded_at).toLowerCase()}`) : "";
  const present = session ? session.attendee_ids.length + (session.unnamed_attendees ?? 0) : 0;

  const audioGone = session?.audio.state === "removed";
  const audioText = session ? audioLine(session.audio) : null;
  const extra = detail ? extraTracks(detail.other_sources, detail.mix) : null;
  const sessionChanged = (next: Session) => setDetail((d) => (d ? { ...d, session: next } : d));
  const audioAction = (action: () => Promise<Session>) => () =>
    action().then(sessionChanged, (e: Error) => setMenuError(e.message));

  const reading = !error && (!detail || (attributeRun !== null && !view && !transcriptError));

  return (
    <div className="cl-review" data-audio-gone={audioGone || undefined}>
      {/* Once the audio is deleted there is nothing to load (spec §7.10). */}
      <audio ref={pb.audioRef} src={audioGone ? undefined : api.audioUrl(id)} preload="metadata" />
      {/* Read, not yet shown: the session, or the version it has. Its shapes meanwhile, then
          the page at once: nothing comes in pieces (the steps, then the transcript). */}
      {reading ? (
        <ReviewSkeleton />
      ) : (
        <>
          <header className="cl-review__header">
            <div className="cl-review__top">
              {session ? (
                <ProjectCrumb
                  session={session}
                  projects={projects}
                  onMoved={(next) => {
                    sessionChanged(next);
                    libraryChanged();
                  }}
                  onError={setMenuError}
                />
              ) : (
                <span />
              )}
              {session && (
                <SessionMenu
                  session={session}
                  onChanged={sessionChanged}
                  onError={setMenuError}
                  onIncomplete={setIncomplete}
                  onDone={setNotice}
                />
              )}
            </div>
            {session && (
              <div>
                <EditableTitle
                  title={title}
                  onSave={async (value) => {
                    await api.renameSession(id, value);
                    await refresh();
                    libraryChanged();
                  }}
                />
                <Text color="secondary">
                  {formatDate(session.recorded_at)} · {formatDuration(session.duration_s)}
                  {present ? ` · ${plural(present, "présent", "présents")}` : ""}
                  {extra && <span title={extra.title}>{extra.text}</span>}
                  {audioText && (
                    <>
                      {" · "}
                      <span data-announced={session.audio.state === "announced" || undefined} className="cl-audio-note">
                        {audioText}
                      </span>
                      {session.audio.state === "announced" && (
                        <>
                          {" · "}
                          <button type="button" className="cl-linkbtn" onClick={audioAction(() => api.keepAudio(id, true))}>
                            Garder l'audio
                          </button>
                          {" · "}
                          <button type="button" className="cl-linkbtn" onClick={audioAction(() => api.extendAudio(id))}>
                            Prolonger
                          </button>
                        </>
                      )}
                    </>
                  )}
                  {!session.title_edited && attributeRun && (
                    <>
                      {" · "}
                      {titleState === "waiting" ? (
                        <span>titre en préparation…</span>
                      ) : (
                        <button type="button" className="cl-linkbtn" onClick={askTitle}>
                          {session.title ? "Proposer un autre titre" : "Proposer un titre"}
                        </button>
                      )}
                    </>
                  )}
                </Text>
                {titleState && titleState !== "waiting" && <p className="cl-title__error">{titleState}</p>}
              </div>
            )}
            {session && view && (
              <PhaseStrip
                view={view}
                duration={session.duration_s ?? 0}
                time={pb.time}
                status={phasesStatus}
                dev={dev}
                onSeek={pb.seek}
                onDetect={() => {
                  api.detectPhases(id).then(setPhasesStatus, (e: Error) => setError(e.message));
                }}
              />
            )}
          </header>

          {error && (
            <div className="cl-review__notice">
              <Banner status="error" title="Séance illisible" description={error} />
            </div>
          )}
          {incomplete && (
            <div className="cl-review__notice">
              <Banner status="warning" title="Suppression incomplète" description={incomplete} isDismissable onDismiss={() => setIncomplete(null)} />
            </div>
          )}
          {stopProblem && (
            <div className="cl-review__notice">
              <Banner
                status="warning"
                title="À l'arrêt de l'enregistrement"
                description={stopProblem}
                isDismissable
                onDismiss={() => setStopProblem(null)}
              />
            </div>
          )}
          {menuError && (
            <div className="cl-review__notice">
              <Banner status="error" title="Refusé" description={menuError} isDismissable onDismiss={() => setMenuError(null)} />
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
              onProcess={async () => {
                await api.processSession(id);
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
                        title="Correction refusée"
                        description={editError}
                        isDismissable
                        onDismiss={() => setEditError(null)}
                      />
                    </div>
                  )}
                  <RerunNotices
                    detail={detail}
                    view={view}
                    onResume={async (attendees) => {
                      await api.resume(id, attendees);
                      await refresh();
                    }}
                    onShowList={() => {
                      setTab("overview");
                      // Once the tab is drawn: the list, in view.
                      window.setTimeout(
                        () => document.getElementById("non-reportees")?.scrollIntoView({ behavior: "smooth", block: "start" }),
                        50,
                      );
                    }}
                  />
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
                  <KeyFigures view={view} model={model} dev={dev} />
                  <Participants
                    model={model}
                    onMerge={(source, target) => correct({ kind: "merge_speakers", source, target })}
                  />
                  <NotesSection sessionId={id} />
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
                    onUndo={async (editId) => {
                      try {
                        setView(await api.undo(id, editId, view.run_id));
                      } catch (e) {
                        refused(e);
                      }
                    }}
                    onRedo={async (editId) => {
                      try {
                        setView(await api.redo(id, editId, view.run_id));
                      } catch (e) {
                        refused(e);
                      }
                    }}
                  />
                  <VersionsSection
                    sessionId={id}
                    version={attributeRun}
                    busy={busy}
                    carryover={view.carryover}
                    duration={session.duration_s}
                    dev={dev}
                    onChanged={refresh}
                    onSeek={pb.seek}
                  />
                  {(dev ||
                    busy ||
                    detail.stages.some(
                      (s) => s.state === "failed" || s.state === "stalled" || s.folder_missing || s.stale,
                    )) && (
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
              {audioGone ? (
                <div className="cl-player-gone" role="status">
                  <Text color="secondary">
                    L'audio de cette séance a été supprimé{audioText ? ` (${audioText.replace("audio supprimé ", "")})` : ""} : la lecture n'est plus possible. Le texte reste modifiable.
                  </Text>
                </div>
              ) : (
                <PlayerBar model={model} pb={pb} current={currentRow} />
              )}
            </>
          )}
        </>
      )}
      <ProvenanceDialog sessionId={id} stage={provenanceOf} onClose={() => setProvenanceOf(null)} />
    </div>
  );
}

const SEEN_KEY = "coulisses.report-vu.";

function carryoverSeen(runId: string): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY + runId) === "1";
  } catch {
    return false; // storage blocked: the notice shows again, nothing is lost
  }
}

/** Above the transcript, while a stage is run again and once it is: the version shown
 *  stays until the new one is complete (in progress, or stopped with its error and
 *  « Reprendre »), then what was carried over to the new one, and what was not (P8). */
function RerunNotices({
  detail,
  view,
  onResume,
  onShowList,
}: {
  detail: SessionDetail;
  view: CorrectedView;
  onResume: (attendees?: number) => Promise<void>;
  onShowList: () => void;
}) {
  const dev = useDevMode();
  const [seen, setSeen] = useState(() => carryoverSeen(view.run_id));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setSeen(carryoverSeen(view.run_id)), [view.run_id]);
  const { session, rerun } = detail;
  const notices: ReactNode[] = [];

  if (rerun && (session.job_state === "queued" || session.job_state === "running")) {
    const running = detail.stages.find((s) => s.state === "running");
    const progress =
      running?.progress && running.progress.total > 0
        ? ` (${Math.round((100 * running.progress.done) / running.progress.total)} %)`
        : "";
    // A rerun going as it should: said quietly, not as an alert.
    notices.push(
      <div key="running" className="cl-rerunning" role="status">
        <Spinner size="sm" shade="subtle" aria-label="Relance en cours" />
        <div>
          <Text weight="medium">
            Relance de {RERUN_NAME[rerun]} en cours
            {session.job_state === "queued" ? " : en file d'attente" : running ? ` : « ${running.label} »${progress}` : ""}
          </Text>
          <Text as="p" type="supporting">
            La version affichée reste en place ; à la fin, vos corrections sont reportées sur la
            nouvelle.
          </Text>
        </div>
      </div>,
    );
  }
  // The audio deleted since: the rerun cannot be resumed, nothing is offered (spec §7.10).
  if (rerun && session.job_state === "failed" && session.audio.state !== "removed") {
    const failed = detail.stages.find((s) => s.state === "failed");
    const why = dev
      ? (session.job_error ?? "Erreur inconnue")
      : failed
        ? `« ${failed.label} » : ${describeStageError(failed) ?? "échec"}`
        : (session.job_error ?? "Erreur inconnue");
    const found = Number(failed?.error_details?.found);
    const fewer = failed?.error_code === "too_few_speakers" && Number.isFinite(found) && found >= 1;
    const resume = async () => {
      try {
        await onResume(fewer ? found : undefined);
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      }
    };
    notices.push(
      <Banner
        key="failed"
        status="error"
        title={`La relance de ${RERUN_NAME[rerun]} n'est pas allée au bout`}
        description={`${why.replace(/\.?$/, ".")} La version affichée n'a pas changé.${error ? ` ${error}` : ""}`}
        endContent={
          <Button
            size="sm"
            variant="primary"
            label={fewer ? `Reprendre avec ${plural(found, "présent", "présents")}` : "Reprendre"}
            clickAction={resume}
          />
        }
      />,
    );
  }
  const carried = view.carryover;
  if (carried && !seen) {
    const missing = carried.not_carried.length;
    const done = plural(carried.carried, "correction reportée", "corrections reportées");
    const dismiss = () => {
      try {
        window.localStorage.setItem(SEEN_KEY + view.run_id, "1");
      } catch {
        // Storage blocked: hidden for this page only.
      }
      setSeen(true);
    };
    notices.push(
      <Banner
        key="carried"
        status={missing ? "warning" : "success"}
        title="Nouvelle version"
        description={
          missing
            ? `${done} depuis la version précédente ; ${plural(missing, "est", "sont")} à reprendre à la main.`
            : `${done} depuis la version précédente.`
        }
        isDismissable
        onDismiss={dismiss}
        endContent={
          missing ? <Button size="sm" label="Voir la liste" onClick={onShowList} /> : undefined
        }
      />,
    );
  }
  if (!notices.length) return null;
  return <div className="cl-review__notice cl-review__notices">{notices}</div>;
}

function ProcessingPanel({
  detail,
  transcriptError,
  onResume,
  onShowProvenance,
  onProcess,
}: {
  detail: SessionDetail;
  transcriptError: string | null;
  onResume: (attendees?: number) => Promise<void>;
  onProcess: () => Promise<void>;
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
  // The audio deleted (by hand, or never processed and deleted): nothing can be resumed.
  const gone = session.audio.state === "removed";
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
      {gone ? (
        <Banner
          status="info"
          title="Audio supprimé"
          description="L'audio de cette séance a été supprimé avant la fin de son traitement : il n'y a plus rien à traiter. La séance peut être supprimée depuis le menu « … »."
        />
      ) : (
        session.job_state === null && <NotProcessed detail={detail} onProcess={onProcess} />
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
      {failed && !gone && (
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
      {failed && tooFew && !gone && (
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
      {detail.source && !detail.source.file_present && !gone && (
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

/** A recording not processed yet: still being recorded, stopped on battery (spec §7.4:
 *  the user decides), or repaired after a crash. Never an import, processed at once. */
function NotProcessed({ detail, onProcess }: { detail: SessionDetail; onProcess: () => Promise<void> }) {
  const source = detail.source;
  const [battery, setBattery] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.power().then(
      (p) => setBattery(p.on_battery),
      (e: Error) => setError(`Impossible de savoir si le Mac est branché : ${e.message}`),
    );
  }, []);
  if (source?.capture_state === "recording") {
    return (
      <Banner
        status="info"
        title="Enregistrement en cours"
        description="Cette séance est en train d'être enregistrée."
        endContent={<Button size="sm" label="Y aller" onClick={() => (window.location.hash = "#/enregistrement")} />}
      />
    );
  }
  if (source?.origin !== "captured") {
    return (
      <Banner
        status="warning"
        title="Aucun traitement n'a été demandé pour cet enregistrement"
        description="Cela ne devrait pas arriver après un import : signalez-le."
      />
    );
  }
  if (source.duration_s === null) {
    return (
      <Banner
        status="error"
        title="Fichier illisible"
        description={`Le fichier de cet enregistrement (${source.file_name}) n'a pas pu être relu. Il reste dans le dossier de la séance ; rien n'a été effacé.`}
      />
    );
  }
  if (!source.duration_s) {
    return (
      <Banner
        status="warning"
        title="Rien n'a été enregistré"
        description="Le micro n'a rien donné pendant cet enregistrement : il n'y a rien à traiter."
      />
    );
  }
  const minutes = Math.max(1, Math.round((source.duration_s / 3600) * 10));
  return (
    <div className="cl-notprocessed">
      {source.capture_state === "recovered" && (
        <Banner
          status="warning"
          title="Enregistrement interrompu, récupéré"
          description={`Coulisses s'est arrêté pendant l'enregistrement. Les ${formatDuration(source.duration_s)} écrites sur le disque sont gardées ; au plus quelques secondes manquent à la fin.`}
        />
      )}
      <Text>
        Cette séance n'est pas encore traitée : environ {minutes} min de calcul.
        {battery ? " Le Mac est sur batterie : mieux vaut le brancher avant de lancer le traitement." : ""}
      </Text>
      <div>
        <Button
          label="Traiter maintenant"
          variant="primary"
          clickAction={async () => {
            try {
              await onProcess();
              setError(null);
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        />
      </div>
      {error && <Banner status="error" title="Refusé" description={error} />}
    </div>
  );
}


/** Where the session is: its space, then its project, chosen here to move it (spec
 *  §7.11). The source (captured, imported) is said in passing. */
function ProjectCrumb({
  session,
  projects,
  onMoved,
  onError,
}: {
  session: Session;
  projects: Project[];
  onMoved: (session: Session) => void;
  onError: (message: string) => void;
}) {
  const own = projects.filter((p) => p.space_id === session.space_id && (!p.archived || p.id === session.project_id));
  return (
    <div className="cl-crumb">
      <a href={`#/espaces/${session.space_id}`}>{session.space_name}</a>
      <span aria-hidden>·</span>
      <select
        className="cl-crumb__select"
        aria-label="Projet de la séance"
        value={session.project_id ?? ""}
        onChange={(e) => {
          const next = e.target.value ? Number(e.target.value) : null;
          api.setSessionProject(session.id, next).then(onMoved, (err: Error) => onError(err.message));
        }}
      >
        <option value="">Aucun projet</option>
        {own.map((p) => (
          <option key={p.id} value={p.id} disabled={p.archived}>
            {p.name}
            {p.archived ? " (archivé)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
