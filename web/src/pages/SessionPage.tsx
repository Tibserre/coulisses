import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import {
  MetadataList,
  MetadataListItem,
} from "@astryxdesign/core/MetadataList";
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
  type Speaker,
  type StageView,
} from "../api.ts";
import type { TurnRow } from "../transcript.ts";
import { PhaseStrip } from "../components/PhaseStrip.tsx";
import { PlayerBar } from "../components/PlayerBar.tsx";
import { ReviewSkeleton } from "../components/ReviewSkeleton.tsx";
import { SpeakerFocusBar } from "../components/SpeakerFocus.tsx";
import { NamingBar } from "../components/NamingBar.tsx";
import { EXCERPT_S, NamingCard } from "../components/NamingCard.tsx";
import { ProvenanceDialog } from "../components/ProvenanceDialog.tsx";
import {
  CorrectionsHistory,
  KeyFigures,
  Attendees,
} from "../components/ReviewSide.tsx";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import {
  BatteryMedium,
  ChevronDown,
  Hourglass,
  UserRoundSearch,
} from "lucide-react";
import {
  ProcessingOutline,
  RerunRunning,
} from "../components/ProcessingOutline.tsx";
import { StageList } from "../components/StageList.tsx";
import { AttendeesAsk } from "../components/AttendeesAsk.tsx";
import {
  GiveToPanel,
  TranscriptView,
  inkOf,
  type Editing,
} from "../components/TranscriptView.tsx";
import { SummaryView } from "../components/SummaryView.tsx";
import {
  RerunDialog,
  VersionsSection,
} from "../components/VersionsSection.tsx";
import { SessionMenu } from "../components/SessionMenu.tsx";
import { audioLine } from "../retention.ts";
import { libraryChanged } from "../library.ts";
import { RERUN_NAME, attendeesNotTaken } from "../versions.ts";
import { extraTracks } from "../tracks.ts";
import { takeStopProblem } from "../stopNotice.ts";
import { EditableTitle } from "../components/EditableTitle.tsx";
import { formatBytes, formatDate, formatDuration, plural } from "../format.ts";
import {
  buildModel,
  changesChapters,
  focusModel,
  namingLines,
  voiceTurns,
  voicesToName,
  liveEditsKey,
  phaseOf,
  toggleSelection,
  turnAt,
  speakerMarks,
  wordAt,
} from "../transcript.ts";
import { usePlayback } from "../usePlayback.ts";
import { useDevMode } from "../devMode.ts";
import { describeStageError } from "../errors.ts";

/** Keys typed into a text field keep their meaning; on a button or a checkbox, N and E
 *  still work. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (
    target.isContentEditable ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  )
    return true;
  if (target instanceof HTMLInputElement)
    return !["checkbox", "radio", "range", "button"].includes(target.type);
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
  // One reading at a time (ADR 0060): the transcript, or the summaries. The page opens on
  // the transcript; a search hit in a summary opens the summaries.
  const [reading, setReading] = useState<"transcript" | "summary">(
    initialTab === "summary" ? "summary" : "transcript",
  );
  useEffect(() => {
    if (initialTab === "summary") setReading("summary");
  }, [initialTab]);
  /** Read once: kept drawn after, so that coming back finds it as it was left. */
  const [summaryDrawn, setSummaryDrawn] = useState(initialTab === "summary");
  useEffect(() => {
    if (reading === "summary") setSummaryDrawn(true);
  }, [reading]);
  // The details of the session, each where it is looked for (ADR 0062): the attendees in
  // the breadcrumb, the corrections beside the switch, the versions in « ⋯ ».
  const [attendeesOpen, setAttendeesOpen] = useState(false);
  const [correctionsOpen, setCorrectionsOpen] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [rerunFrom, setRerunFrom] = useState<"all" | "diarize">("all");
  const openVersions = (part?: string) => {
    setVersionsOpen(true);
    if (part)
      // Once it is drawn: that part, in view.
      window.setTimeout(
        () =>
          document
            .getElementById(part)
            ?.scrollIntoView({ behavior: "smooth", block: "start" }),
        80,
      );
  };
  /** The guided naming (ADR 0062): the voice named, and which of its lines is looked at. */
  const [guide, setGuide] = useState<{
    label: string;
    /** The line looked at, by its index in the run; null: where the voice is heard best. */
    turn: number | null;
    /** Its place among the voices to name: the next one is taken from there. */
    at: number;
    /** The voices there were to name when it began, and how many are named since. */
    total: number;
    named: number;
  } | null>(null);
  /** « Écouter … à la suite »: the lines being heard one after the other, and which one. */
  const [queue, setQueue] = useState<{ rows: TurnRow[]; step: number } | null>(
    null,
  );
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
  // Processed while the page was open (ADR 0058): the names settle on the text, once.
  const [arrived, setArrived] = useState(false);
  const wasBusy = useRef(false);
  useEffect(() => {
    if (busy) {
      wasBusy.current = true;
      setArrived(false);
      return;
    }
    if (!wasBusy.current || jobState !== "done") return;
    wasBusy.current = false;
    setArrived(true);
    // As long as the moment of the voices lasts (index.css, .cl-arrival).
    const timer = window.setTimeout(() => setArrived(false), 3400);
    return () => window.clearTimeout(timer);
  }, [busy, jobState]);

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
  const phasesWaiting =
    phasesStatus?.state === "queued" || phasesStatus?.state === "running";
  useEffect(() => {
    if (!phasesWaiting) return;
    const timer = window.setInterval(() => void loadPhases(), 3000);
    return () => {
      window.clearInterval(timer);
      // Over: the transcript gets its chapters.
      api
        .transcript(id)
        .then(setView, (e: Error) => setTranscriptError(e.message));
    };
  }, [phasesWaiting, loadPhases, id]);

  // The title is proposed on demand, from the chapters (ADR 0026): asked, then followed
  // until it is there. A failure says why, next to the title.
  const [titleState, setTitleState] = useState<"waiting" | string | null>(null);
  const titleBefore = useRef<string | null>(null);
  const askTitle = () => {
    titleBefore.current = detail?.session.title ?? null;
    setTitleState("waiting");
    api
      .requestGeneration(id, "titre", null)
      .catch((e: Error) => setTitleState(e.message));
  };
  useEffect(() => {
    if (titleState !== "waiting") return;
    const timer = window.setInterval(() => {
      api.generations(id).then(
        (g) => {
          const job = g.pending.find((p) => p.action_ref === "titre");
          if (job?.state === "failed")
            setTitleState(
              `Pas de titre proposé : ${job.error ?? "erreur inconnue"}`,
            );
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

  // The chapters being written (ADR 0061): shown in place of the ones in force, as the
  // detection finds them; never changed until they are set.
  const provisional =
    phasesStatus?.state === "running" &&
    (phasesStatus.provisional?.length ?? 0) > 0;
  const read = useMemo(
    () =>
      view && provisional
        ? { ...view, phases: phasesStatus!.provisional! }
        : view,
    [view, provisional, phasesStatus],
  );
  // During playback, the chapter being heard stays open, even folded (art direction).
  const unfolded = useMemo(() => (read ? buildModel(read) : null), [read]);
  const heard = unfolded && pb.playing ? turnAt(unfolded, pb.time) : null;
  const heardChapter =
    read && heard
      ? (phaseOf(read.phases, heard.turn.index)?.turn ?? null)
      : null;
  const model = useMemo(() => {
    if (!read) return null;
    // Chapters being written cannot be unfolded (their heading is read only): all open.
    const shut = provisional
      ? new Set<number>()
      : new Set([...folded].filter((t) => t !== heardChapter));
    return shut.size ? buildModel(read, shut) : unfolded;
  }, [read, folded, heardChapter, unfolded, provisional]);
  // One voice shown only (its lines, the others folded), and the voice pointed at in the
  // side column: where it speaks is marked on the player bar.
  const [focus, setFocus] = useState<string | null>(null);
  const [pointed, setPointed] = useState<string | null>(null);
  const shown = useMemo(
    () => (focus && unfolded ? focusModel(unfolded, focus) : model),
    [focus, unfolded, model],
  );
  const focused = focus
    ? (unfolded?.speakers.find((s) => s.label === focus) ?? null)
    : null;
  // The voice merged into another one: back to all of them.
  useEffect(() => {
    if (focus && unfolded && !focused) setFocus(null);
  }, [focus, unfolded, focused]);
  const marked = pointed ?? focus;
  const marks = useMemo(
    () => (marked && unfolded ? speakerMarks(unfolded, marked) : []),
    [marked, unfolded],
  );
  const markInk = marked
    ? unfolded?.speakers.find((s) => s.label === marked)
    : undefined;
  const currentRow = shown ? turnAt(shown, pb.time) : null;

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
  const current = currentRow
    ? { row: currentRow, word: wordAt(currentRow, pb.time) }
    : null;

  /** A correction refused. Meant for a version no longer shown (409): nothing was
   *  written; the page reads the version now shown, and a typed text is given back. */
  const refused = useCallback(
    (e: unknown, typed?: string) => {
      const error = e as Error;
      if (error instanceof ServiceError && error.status === 409) {
        setEditingTurn(null);
        setTyping(false);
        setEditError(
          `${error.message}${typed ? ` Votre texte, à reprendre : « ${typed} »` : ""}`,
        );
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
      if (provisional && changesChapters(correction)) {
        setEditError(
          "Les chapitres s'écrivent encore : ils se modifient une fois fixés.",
        );
        return;
      }
      try {
        const next = await api.addEdit(id, correction, viewRun);
        setView(next);
        setEditError(null);
        // Naming a voice after a person who already has one merges them: said on screen.
        const last = next.edits.at(-1);
        if (
          correction.kind === "assign_speaker" &&
          last?.kind === "merge_speakers"
        )
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
    [id, viewRun, refused, provisional],
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
        if (guide) return; // naming, guided: no selection (its bar would be hidden)
        const order = shown
          ? shown.rows.flatMap((r) => (r.kind === "turn" ? [r.turn.index] : []))
          : [];
        setSelected((before) =>
          toggleSelection(before, order, turn, extend ? lastSelected : null),
        );
        setLastSelected(turn);
      },
      setTyping,
      chaptersProvisional: provisional,
      showSpeaker: (label: string) => {
        setNamingTurn(null);
        setFocus(label);
      },
      toggleFolded: (turn: number) =>
        setFolded((before) => {
          const next = new Set(before);
          if (!next.delete(turn)) next.add(turn);
          return next;
        }),
    }),
    [
      people,
      correct,
      spaceId,
      loadPeople,
      id,
      editingTurn,
      namingTurn,
      selected,
      lastSelected,
      shown,
      viewRun,
      refused,
      provisional,
      guide,
    ],
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
          const target = edits
            .filter((e) => !e.reverted)
            .sort((a, b) => b.id - a.id)[0];
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
      // The guided naming, its field left (a click on one of its buttons): Escape ends it.
      if (e.key === "Escape" && guide) {
        e.preventDefault();
        setGuide(null);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        void history(e.shiftKey);
        return;
      }
      // The other keys are the bar's while it is there.
      if (guide) return;
      // Escape: back to all the voices (a name being typed handles its own Escape).
      if (e.key === "Escape" && focus) {
        e.preventDefault();
        setFocus(null);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || !currentRow) return;
      if (reading !== "transcript") return;
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        setNamingTurn(currentRow.turn.index);
      } else if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        setEditingTurn(currentRow.turn.index);
      } else if (e.key === "c" || e.key === "C") {
        e.preventDefault();
        void correct({ kind: "set_phase", turn: currentRow.turn.index }).catch(
          () => undefined,
        );
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [currentRow, history, correct, focus, reading, guide]);

  const session = detail?.session;
  const title = session
    ? (session.title ??
      `Séance du ${formatDate(session.recorded_at).toLowerCase()}`)
    : "";
  const present = session
    ? session.attendee_ids.length + (session.unnamed_attendees ?? 0)
    : 0;

  const voices = unfolded?.speakers.filter((s) => s.label !== null) ?? [];
  const toName = useMemo(
    () => (unfolded ? voicesToName(unfolded) : []),
    [unfolded],
  );
  const liveEdits = view?.edits.filter((e) => !e.reverted).length ?? 0;
  const speechTotal = voices.reduce((sum, v) => sum + v.seconds, 0) || 1;
  // Two voices named after the same person (the engine split one person, P3): offered a
  // merge, never done alone.
  const twins: [Speaker, Speaker][] = voices.flatMap((v, i) => {
    if (v.person_id == null || v.character) return [];
    const first = voices
      .slice(0, i)
      .find((o) => o.person_id === v.person_id && !o.character);
    return first ? [[first, v] as [Speaker, Speaker]] : [];
  });

  // The guided naming goes on to the next voice once one is named (or merged).
  const guided = guide
    ? (unfolded?.speakers.find((s) => s.label === guide.label) ?? null)
    : null;
  useEffect(() => {
    if (!guide || (guided && !guided.named)) return;
    // Named (or merged): gone from the list, the next one takes its place.
    setQueue(null);
    const next = toName[guide.at] ?? toName[0];
    setGuide(
      next?.label
        ? {
            ...guide,
            label: next.label,
            turn: null,
            at: toName.indexOf(next),
            named: guide.named + 1,
          }
        : null,
    );
  }, [guide, guided, toName]);
  /** A line of the voice heard (or stopped, if it is being heard); a queue stops. */
  const hearLine = (row: TurnRow) => {
    setQueue(null);
    if (!guide) return;
    setGuide({ ...guide, turn: row.turn.index });
    const { start, end } = row.turn;
    if (start != null && !audioGone) pb.listen(start, end ?? start + EXCERPT_S);
    // Not to be heard: what was being heard stops, nothing goes on unasked.
    else if (pb.excerpt != null) pb.listen(pb.excerpt, pb.excerpt);
  };
  /** ← → from the field: the voice's line before or after in time (as on its strip),
   *  heard. */
  const moveGuide = (by: number) => {
    if (!guideTurn || !guideTurns.length) return;
    const at = guideTurns.indexOf(guideTurn);
    hearLine(guideTurns[(at + by + guideTurns.length) % guideTurns.length]);
  };
  // The queue: each excerpt over, the next one (stopping by hand clears it first).
  const excerptBefore = useRef<number | null>(null);
  useEffect(() => {
    const before = excerptBefore.current;
    excerptBefore.current = pb.excerpt;
    if (!queue || before === null || pb.excerpt !== null) return;
    const step = queue.step + 1;
    const next = queue.rows[step];
    if (!next || next.turn.start == null || !guide) {
      setQueue(null);
      return;
    }
    setQueue({ rows: queue.rows, step });
    setGuide({ ...guide, turn: next.turn.index });
    pb.listen(next.turn.start, next.turn.end ?? next.turn.start + EXCERPT_S);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on each excerpt's end only
  }, [pb.excerpt]);
  const stopHearing = () => {
    setQueue(null);
    if (pb.excerpt != null) pb.listen(pb.excerpt, pb.excerpt);
  };
  const startNaming = () => {
    const first = toName[0];
    if (!first?.label) return;
    setReading("transcript");
    setFocus(null);
    setNamingTurn(null);
    // The bar takes the place of the selection's: none while naming.
    setSelected(new Set());
    setQueue(null);
    setGuide({
      label: first.label,
      turn: null,
      at: 0,
      total: toName.length,
      named: 0,
    });
  };
  const guideTurns = guide && unfolded ? voiceTurns(unfolded, guide.label) : [];
  // The line looked at: the one picked, else where the voice is heard best.
  const guideTurn =
    guideTurns.find((r) => r.turn.index === guide?.turn) ??
    namingLines(guideTurns, "long")[0] ??
    null;

  const audioGone = session?.audio.state === "removed";
  const audioText = session ? audioLine(session.audio) : null;
  const extra = detail ? extraTracks(detail.other_sources, detail.mix) : null;
  const sessionChanged = (next: Session) =>
    setDetail((d) => (d ? { ...d, session: next } : d));
  const audioAction = (action: () => Promise<Session>) => () =>
    action().then(sessionChanged, (e: Error) => setMenuError(e.message));

  const loading =
    !error && (!detail || (attributeRun !== null && !view && !transcriptError));

  return (
    <div className="cl-review" data-audio-gone={audioGone || undefined}>
      {/* Once the audio is deleted there is nothing to load (spec §7.10). */}
      <audio
        ref={pb.audioRef}
        src={audioGone ? undefined : api.audioUrl(id)}
        preload="metadata"
      />
      {/* Read, not yet shown: the session, or the version it has. Its shapes meanwhile, then
          the page at once: nothing comes in pieces (the steps, then the transcript). */}
      {loading ? (
        <ReviewSkeleton />
      ) : (
        <>
          <header
            className="cl-review__header"
            inert={guide ? true : undefined}
          >
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
                <Popover
                  isOpen={attendeesOpen}
                  onOpenChange={setAttendeesOpen}
                  label="Présents"
                  width={300}
                  content={
                    <div className="cl-pop">
                      <Attendees
                        session={session}
                        people={people}
                        inline
                        onSave={async (ids, unnamed) => {
                          await api.setAttendees(id, ids, unnamed);
                          await refresh();
                        }}
                      />
                      {(() => {
                        const said = attendeesNotTaken(session);
                        return (
                          said && (
                            <div className="cl-pop__aside">
                              <Text type="supporting">{said.text}</Text>
                              {said.rerun && (
                                <div>
                                  <Button
                                    label="Refaire les voix…"
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => {
                                      setAttendeesOpen(false);
                                      setRerunFrom("diarize");
                                      setRerunOpen(true);
                                    }}
                                  />
                                </div>
                              )}
                            </div>
                          )
                        );
                      })()}
                    </div>
                  }
                >
                  <button type="button" className="cl-crumbbtn">
                    {present
                      ? plural(present, "présent", "présents")
                      : "Présents"}
                    <ChevronDown size={13} strokeWidth={1.75} aria-hidden />
                  </button>
                </Popover>
              )}
              {session && (
                <SessionMenu
                  onVersions={() => openVersions()}
                  onRerun={() => {
                    setRerunFrom("all");
                    setRerunOpen(true);
                  }}
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
                  {formatDate(session.recorded_at)} ·{" "}
                  {formatDuration(session.duration_s)}
                  {extra && <span title={extra.title}>{extra.text}</span>}
                  {audioText && (
                    <>
                      {" · "}
                      <span
                        data-announced={
                          session.audio.state === "announced" || undefined
                        }
                        className="cl-audio-note"
                      >
                        {audioText}
                      </span>
                      {session.audio.state === "announced" && (
                        <>
                          {" · "}
                          <button
                            type="button"
                            className="cl-linkbtn"
                            onClick={audioAction(() => api.keepAudio(id, true))}
                          >
                            Garder l'audio
                          </button>
                          {" · "}
                          <button
                            type="button"
                            className="cl-linkbtn"
                            onClick={audioAction(() => api.extendAudio(id))}
                          >
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
                        <button
                          type="button"
                          className="cl-linkbtn"
                          onClick={askTitle}
                        >
                          {session.title
                            ? "Proposer un autre titre"
                            : "Proposer un titre"}
                        </button>
                      )}
                    </>
                  )}
                </Text>
                {titleState && titleState !== "waiting" && (
                  <p className="cl-title__error">{titleState}</p>
                )}
              </div>
            )}
            {session && voices.length > 0 && (
              // The voices and their share of the speech; a click shows a voice's lines
              // only. The ones without a name are named, guided, from here (ADR 0062).
              <div className="cl-voices" aria-label="Participants">
                {voices
                  .filter((v) => v.named)
                  .map((v) => (
                    <button
                      key={v.label}
                      type="button"
                      className="cl-voice"
                      aria-pressed={focus === v.label}
                      title={`N'afficher que les répliques de ${v.name}`}
                      onClick={() => {
                        setReading("transcript");
                        setFocus(focus === v.label ? null : v.label);
                      }}
                      onPointerEnter={() => setPointed(v.label)}
                      onPointerLeave={() => setPointed(null)}
                    >
                      <span className="cl-name" style={{ color: inkOf(v) }}>
                        {v.name}
                      </span>
                      <span className="cl-voice__share">
                        {(100 * v.seconds) / speechTotal < 1
                          ? "< 1 %"
                          : `${Math.round((100 * v.seconds) / speechTotal)} %`}
                      </span>
                    </button>
                  ))}
                {twins.map(([a, b]) => (
                  <button
                    key={`${a.label}+${b.label}`}
                    type="button"
                    className="cl-voice"
                    data-merge
                    title={`Deux voix portent le nom ${a.name} : les réunir en une seule (Cmd-Z pour annuler)`}
                    onClick={() =>
                      void correct({
                        kind: "merge_speakers",
                        source: b.label!,
                        target: a.label!,
                      }).catch(() => undefined)
                    }
                  >
                    Fusionner les deux {a.name}
                  </button>
                ))}
                {toName.length > 0 && !guide && (
                  <button
                    type="button"
                    className="cl-voice"
                    data-todo
                    onClick={startNaming}
                  >
                    <UserRoundSearch size={14} strokeWidth={1.75} aria-hidden />
                    {plural(toName.length, "voix à nommer", "voix à nommer")}
                  </button>
                )}
                {view?.voices_problem && (
                  <span className="cl-voices__problem">
                    {view.voices_problem}
                  </span>
                )}
              </div>
            )}
            {session && view && (
              <PhaseStrip
                view={read ?? view}
                provisional={provisional}
                duration={session.duration_s ?? 0}
                time={pb.time}
                status={phasesStatus}
                dev={dev}
                onSeek={pb.seek}
                onDetect={() => {
                  api
                    .detectPhases(id)
                    .then(setPhasesStatus, (e: Error) => setError(e.message));
                }}
              />
            )}
            {session && model && view && (
              <div className="cl-review__views">
                <div className="cl-seg" role="tablist" aria-label="Lire">
                  {(
                    [
                      ["transcript", "Transcription"],
                      ["summary", "Résumé"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      role="tab"
                      aria-selected={reading === value}
                      onClick={() => setReading(value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <span className="cl-review__viewtools">
                  {reading === "transcript" && view.edits.length > 0 && (
                    <Popover
                      isOpen={correctionsOpen}
                      onOpenChange={setCorrectionsOpen}
                      label="Corrections"
                      width={340}
                      content={
                        <div className="cl-pop">
                          <CorrectionsHistory
                            edits={view.edits}
                            onUndo={async (editId) => {
                              try {
                                setView(
                                  await api.undo(id, editId, view.run_id),
                                );
                              } catch (e) {
                                refused(e);
                              }
                            }}
                            onRedo={async (editId) => {
                              try {
                                setView(
                                  await api.redo(id, editId, view.run_id),
                                );
                              } catch (e) {
                                refused(e);
                              }
                            }}
                          />
                        </div>
                      }
                    >
                      <button type="button" className="cl-crumbbtn">
                        {liveEdits
                          ? plural(liveEdits, "correction", "corrections")
                          : "Corrections"}
                        <ChevronDown size={13} strokeWidth={1.75} aria-hidden />
                      </button>
                    </Popover>
                  )}
                </span>
              </div>
            )}
          </header>

          {error && (
            <div className="cl-review__notice">
              <Banner
                status="error"
                title="Séance illisible"
                description={error}
              />
            </div>
          )}
          {incomplete && (
            <div className="cl-review__notice">
              <Banner
                status="warning"
                title="Suppression incomplète"
                description={incomplete}
                isDismissable
                onDismiss={() => setIncomplete(null)}
              />
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
              <Banner
                status="error"
                title="Refusé"
                description={menuError}
                isDismissable
                onDismiss={() => setMenuError(null)}
              />
            </div>
          )}
          {detail && !model && (
            <ProcessingPanel
              detail={detail}
              people={people}
              onSaveAttendees={async (ids, unnamed) => {
                try {
                  await api.setAttendees(id, ids, unnamed);
                } finally {
                  await refresh();
                }
              }}
              onLaunch={async () => {
                await api.launch(id);
                await refresh();
              }}
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
              <div
                className="cl-review__columns"
                inert={guide ? true : undefined}
                data-arrived={arrived || undefined}
              >
                {/* Said in both readings: what was refused or not carried over, and what an
                    undo did, never hidden in the one not shown (P8). */}
                <div className="cl-review__shared">
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
                    onShowList={() => openVersions("non-reportees")}
                  />
                </div>
                <div
                  className="cl-review__main"
                  hidden={reading !== "transcript"}
                >
                  {arrived && <VoicesArrival speakers={model.speakers} />}
                  {focused && shown && (
                    <SpeakerFocusBar
                      speaker={focused}
                      shown={shown}
                      pb={pb}
                      current={currentRow}
                      onName={() => {
                        const first = shown.rows.find((r) => r.kind === "turn");
                        if (first?.kind === "turn")
                          setNamingTurn(first.turn.index);
                      }}
                      onClose={() => setFocus(null)}
                    />
                  )}
                  <TranscriptView
                    model={shown!}
                    pb={pb}
                    current={current}
                    editing={editing}
                  />
                  {selected.size > 0 && !guide && (
                    <div
                      className="cl-selection"
                      role="toolbar"
                      aria-label="Répliques sélectionnées"
                    >
                      <Text>
                        {plural(
                          selected.size,
                          "réplique sélectionnée",
                          "répliques sélectionnées",
                        )}
                      </Text>
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
                              void correct({
                                kind: "reassign_turns",
                                turns: [...selected],
                                target,
                              }).then(
                                () => setSelected(new Set()),
                                () => undefined,
                              );
                            }}
                          />
                        }
                      >
                        <Button size="sm" variant="primary" label="Donner à…" />
                      </Popover>
                      <Button
                        size="sm"
                        variant="ghost"
                        label="Désélectionner"
                        onClick={() => setSelected(new Set())}
                      />
                    </div>
                  )}
                </div>
                {summaryDrawn && (
                  <div
                    className="cl-review__summary"
                    hidden={reading !== "summary"}
                  >
                    <div className="cl-measure">
                      <SummaryView
                        sessionId={id}
                        spaceId={session.space_id}
                        transcriptKey={liveEditsKey(view)}
                      />
                    </div>
                  </div>
                )}
                {notice && (
                  <div className="cl-notice" role="status">
                    {notice}
                  </div>
                )}
                <RerunDialog
                  isOpen={rerunOpen}
                  from={rerunFrom}
                  sessionId={id}
                  duration={session.duration_s}
                  onClose={() => setRerunOpen(false)}
                  onAsked={async () => {
                    setRerunOpen(false);
                    await refresh();
                  }}
                />
                <Dialog
                  isOpen={versionsOpen}
                  onOpenChange={(open) => !open && setVersionsOpen(false)}
                  width={560}
                >
                  <DialogHeader
                    title="Versions"
                    onOpenChange={() => setVersionsOpen(false)}
                  />
                  <div className="cl-versions-dialog">
                    {dev && <KeyFigures view={view} model={model} dev={dev} />}
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
                        (s) =>
                          s.state === "failed" ||
                          s.state === "stalled" ||
                          s.folder_missing ||
                          s.stale,
                      )) && (
                      <section>
                        <Heading level={3}>Traitement</Heading>
                        <StageList
                          stages={detail.stages}
                          onShowProvenance={setProvenanceOf}
                        />
                      </section>
                    )}
                    {dev && <SourceInfo detail={detail} />}
                  </div>
                </Dialog>
              </div>
              {/* Out of reach too while naming, guided. */}
              <div
                className="cl-review__player"
                inert={guide ? true : undefined}
              >
                {audioGone ? (
                  <div className="cl-player-gone" role="status">
                    <Text color="secondary">
                      L'audio de cette séance a été supprimé
                      {audioText
                        ? ` (${audioText.replace("audio supprimé ", "")})`
                        : ""}{" "}
                      : la lecture n'est plus possible. Le texte reste
                      modifiable.
                    </Text>
                  </div>
                ) : (
                  <PlayerBar
                    model={shown!}
                    pb={pb}
                    current={currentRow}
                    marks={marks}
                    markInk={markInk ? inkOf(markInk) : undefined}
                    keys={!guide}
                  />
                )}
              </div>
            </>
          )}
        </>
      )}
      {guide && guided && guideTurn && session && unfolded && (
        // Naming, guided (ADR 0062): the page under a veil, out of reach; over it, the card
        // of the voice's lines, and the field of its name, still at the bottom.
        <div className="cl-naming">
          <div className="cl-naming__veil" aria-hidden />
          {notice && (
            // Said over the veil (a naming that merged two voices, P3).
            <div className="cl-notice cl-naming__notice" role="status">
              {notice}
            </div>
          )}
          <NamingCard
            speaker={guided}
            lines={guideTurns}
            current={guideTurn}
            duration={session.duration_s ?? pb.duration ?? 0}
            pb={pb}
            done={guide.named}
            total={guide.total}
            audioGone={audioGone}
            queueing={queue !== null}
            onPick={(row) => {
              stopHearing();
              setGuide({ ...guide, turn: row.turn.index });
            }}
            onHear={hearLine}
            onQueue={(rows) => {
              setQueue({ rows, step: 0 });
              setGuide({ ...guide, turn: rows[0].turn.index });
              const { start, end } = rows[0].turn;
              if (start != null) pb.listen(start, end ?? start + EXCERPT_S);
            }}
            onStop={stopHearing}
          />
          <div className="cl-naming__bar">
            <NamingBar
              speaker={guided}
              dev={dev}
              people={people}
              voices={unfolded.speakers}
              attendees={session.attendee_ids}
              onPrevious={() => moveGuide(-1)}
              onNext={() => moveGuide(1)}
              onHear={() =>
                pb.excerpt != null ? stopHearing() : hearLine(guideTurn)
              }
              onSkip={() => {
                const at = (toName.indexOf(guided) + 1) % toName.length;
                const next = toName[at];
                if (next?.label) {
                  setQueue(null);
                  setGuide({ ...guide, label: next.label, turn: null, at });
                }
              }}
              onClose={() => setGuide(null)}
              onCorrect={correct}
              onAddGuest={editing.addGuest}
            />
          </div>
        </div>
      )}
      <ProvenanceDialog
        sessionId={id}
        stage={provenanceOf}
        onClose={() => setProvenanceOf(null)}
      />
    </div>
  );
}

/** The voices have come (ADR 0058): where the two discs were, one disc whose ring is each
 *  voice's share of the speech the engine measured (an unnamed voice in grey), with their
 *  names; then it fades and its room closes. Shown once, when the processing ends while the
 *  page is open. */
function VoicesArrival({ speakers }: { speakers: Speaker[] }) {
  const heard = speakers.filter((s) => s.seconds > 0);
  const total = heard.reduce((sum, s) => sum + s.seconds, 0);
  if (!total) return null;
  const r = 33;
  const length = 2 * Math.PI * r;
  let before = 0;
  return (
    <div className="cl-arrival" aria-hidden>
      <div>
        <div className="cl-arrival__inner">
          <svg width="72" height="72" viewBox="0 0 72 72">
            <circle cx="36" cy="36" r={r} className="cl-disc__ground" />
            {heard.map((s) => {
              const part = (length * s.seconds) / total;
              const arc = (
                <circle
                  key={s.label ?? "inconnu"}
                  cx="36"
                  cy="36"
                  r={r}
                  fill="none"
                  stroke={inkOf(s)}
                  strokeWidth={5}
                  strokeDasharray={`${Math.max(part - 3, 0.5)} ${length}`}
                  strokeDashoffset={-before}
                  transform="rotate(-90 36 36)"
                />
              );
              before += part;
              return arc;
            })}
          </svg>
          <div className="cl-arrival__legend">
            {heard.map((s) => (
              <span key={s.label ?? "inconnu"}>
                <span
                  className="cl-name"
                  data-unnamed={!s.named || undefined}
                  style={{ color: inkOf(s) }}
                >
                  {s.name}
                </span>{" "}
                <Text type="supporting">
                  {(100 * s.seconds) / total < 1
                    ? "< 1 %"
                    : `${Math.round((100 * s.seconds) / total)} %`}
                </Text>
              </span>
            ))}
          </div>
        </div>
      </div>
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

  if (
    rerun &&
    (session.job_state === "queued" || session.job_state === "running")
  ) {
    // A rerun going as it should: said quietly, not as an alert.
    notices.push(<RerunRunning key="running" detail={detail} rerun={rerun} />);
  }
  // The audio deleted since: the rerun cannot be resumed, nothing is offered (spec §7.10).
  if (
    rerun &&
    session.job_state === "failed" &&
    session.audio.state !== "removed"
  ) {
    const failed = detail.stages.find((s) => s.state === "failed");
    const why = dev
      ? (session.job_error ?? "Erreur inconnue")
      : failed
        ? `« ${failed.label} » : ${describeStageError(failed) ?? "échec"}`
        : (session.job_error ?? "Erreur inconnue");
    const found = Number(failed?.error_details?.found);
    const fewer =
      failed?.error_code === "too_few_speakers" &&
      Number.isFinite(found) &&
      found >= 1;
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
            label={
              fewer
                ? `Reprendre avec ${plural(found, "présent", "présents")}`
                : "Reprendre"
            }
            clickAction={resume}
          />
        }
      />,
    );
  }
  const carried = view.carryover;
  if (carried && !seen) {
    const missing = carried.not_carried.length;
    const done = plural(
      carried.carried,
      "correction reportée",
      "corrections reportées",
    );
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
          missing ? (
            <Button size="sm" label="Voir la liste" onClick={onShowList} />
          ) : undefined
        }
      />,
    );
  }
  if (!notices.length) return null;
  return <div className="cl-review__notice cl-review__notices">{notices}</div>;
}

function ProcessingPanel({
  detail,
  people,
  onSaveAttendees,
  onLaunch,
  transcriptError,
  onResume,
  onShowProvenance,
  onProcess,
}: {
  detail: SessionDetail;
  people: Person[];
  /** An import waiting for its people present (ADR 0069): each change saved, then launched. */
  onSaveAttendees: (ids: number[], unnamed: number | null) => Promise<void>;
  onLaunch: () => Promise<void>;
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
  const running =
    session.job_state === "queued" || session.job_state === "running";
  const attributed = detail.stages.some(
    (s) => s.stage === "attribute" && s.state === "succeeded",
  );
  const tooFew = failedStage?.error_code === "too_few_speakers";
  const found = Number(failedStage?.error_details?.found);
  const [attendees, setAttendees] = useState<number | null>(null);
  const proposed =
    attendees ?? (Number.isFinite(found) && found >= 1 ? found : 1);
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
  const expected = Number(failedStage?.error_details?.expected);
  const [choosing, setChoosing] = useState(false);
  // An error of the application, not of the recording: said in French, its detail in
  // developer mode (P8: shown, never hidden).
  const plain = failedStage
    ? describeStageError(failedStage)
    : "Une erreur de Coulisses a arrêté le traitement : ce n'est pas votre enregistrement. Reprenez ; si elle revient, son détail est en mode développeur.";
  return (
    <main className="cl-processing">
      {gone && (
        <Banner
          status="info"
          title="Audio supprimé"
          description="L'audio de cette séance a été supprimé avant la fin de son traitement : il n'y a plus rien à traiter. La séance peut être supprimée depuis le menu « … »."
        />
      )}
      {!gone && session.job_state === null && (
        <NotProcessed detail={detail} onProcess={onProcess} />
      )}
      {running && session.processing_starts_at && (
        <AttendeesAsk
          session={session}
          people={people}
          startsAt={session.processing_starts_at}
          onSave={onSaveAttendees}
          onLaunch={onLaunch}
        />
      )}
      {running && <ProcessingOutline detail={detail} />}

      {failed && !gone && tooFew && (
        // Fewer voices than people checked: a question, not a failure (ADR 0058). Voices
        // are never merged to reach the count (P3): going on looks for fewer.
        <section className="cl-ask">
          <Heading level={3}>
            {found >= 1
              ? Number.isFinite(expected) && expected > found
                ? `${plural(found, "voix entendue", "voix entendues")}, ${plural(expected, "présent coché", "présents cochés")}`
                : `${plural(found, "voix entendue", "voix entendues")} : moins que de présents cochés`
              : "Aucune voix entendue"}
          </Heading>
          <Text color="secondary">
            {found >= 1
              ? "Quelqu'un n'a peut-être pas parlé. Les voix ne sont jamais fusionnées pour atteindre le compte."
              : "Personne ne semble parler dans cet enregistrement : il n'y a pas de voix à séparer."}
          </Text>
          <div className="cl-ask__actions">
            {found >= 1 && (
              // What the engine heard, recommended: the people checked were one too many.
              <Button
                label={`Relancer avec ${plural(found, "présent", "présents")} (recommandé)`}
                variant="primary"
                clickAction={() => resume(found)}
              />
            )}
            <Button
              label="Choisir un autre nombre"
              variant={found >= 1 ? "secondary" : "primary"}
              onClick={() => setChoosing(!choosing)}
            />
          </div>
          {choosing && (
            <div className="cl-retry">
              <div style={{ width: 200 }}>
                <NumberInput
                  label="Nombre de présents"
                  description="Au moins autant de voix seront cherchées."
                  value={proposed}
                  onChange={(v) =>
                    setAttendees(
                      Number.isFinite(v) && v >= 1 ? Math.round(v) : null,
                    )
                  }
                />
              </div>
              <Button
                label={`Reprendre avec ${plural(proposed, "présent", "présents")}`}
                clickAction={() => resume(proposed)}
              />
            </div>
          )}
        </section>
      )}
      {failed && !gone && !tooFew && (
        <section className="cl-ask">
          <Heading level={3}>Le traitement s'est arrêté</Heading>
          <Text color="secondary">
            {dev
              ? failure
              : `${failedStage ? `« ${failedStage.label} » : ` : ""}${plain}`}
          </Text>
          <Text type="supporting">
            Les étapes réussies sont gardées ; reprendre ne relance que le
            reste.
          </Text>
          <div className="cl-ask__actions">
            <Button
              label="Reprendre"
              variant="primary"
              clickAction={() => resume()}
            />
          </div>
        </section>
      )}
      {resumeError && (
        <Banner
          status="error"
          title="La reprise a échoué"
          description={resumeError}
        />
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
      {/* The stages one by one, with their provenance (P7): in developer mode, and when
          something stopped, to see where. */}
      {(dev ||
        failed ||
        detail.stages.some((s) => s.state === "stalled" || s.stale)) && (
        <StageList stages={detail.stages} onShowProvenance={onShowProvenance} />
      )}
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
function NotProcessed({
  detail,
  onProcess,
}: {
  detail: SessionDetail;
  onProcess: () => Promise<void>;
}) {
  const source = detail.source;
  const [battery, setBattery] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.power().then(
      (p) => setBattery(p.on_battery),
      (e: Error) =>
        setError(`Impossible de savoir si le Mac est branché : ${e.message}`),
    );
  }, []);
  if (source?.capture_state === "recording") {
    return (
      <Banner
        status="info"
        title="Enregistrement en cours"
        description="Cette séance est en train d'être enregistrée."
        endContent={
          <Button
            size="sm"
            label="Y aller"
            onClick={() => (window.location.hash = "#/enregistrement")}
          />
        }
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
      {/* On battery, the processing waits for a click (ADR 0027): said calmly, at a glance. */}
      <div className="cl-wait">
        {battery ? (
          <BatteryMedium size={22} strokeWidth={1.75} aria-hidden />
        ) : (
          <Hourglass size={22} strokeWidth={1.75} aria-hidden />
        )}
        <div className="cl-wait__text">
          <Text>
            {battery
              ? "Le Mac est sur batterie : le traitement attend votre accord."
              : "Cette séance n'est pas encore traitée."}
          </Text>
          <Text type="supporting">
            Environ {minutes} min de calcul
            {battery ? " ; mieux vaut brancher le Mac d'abord." : "."}
          </Text>
        </div>
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
  const own = projects.filter(
    (p) =>
      p.space_id === session.space_id &&
      (!p.archived || p.id === session.project_id),
  );
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
          api
            .setSessionProject(session.id, next)
            .then(onMoved, (err: Error) => onError(err.message));
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

