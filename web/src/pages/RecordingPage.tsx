import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { Tooltip } from "@astryxdesign/core/Tooltip";
import {
  MicOff,
  Monitor,
  MonitorOff,
  Pause,
  Play,
  Square,
  Star,
} from "lucide-react";
import {
  api,
  type Marker,
  type MarkerKind,
  type Person,
  type Project,
  type RecordingState,
  type Session,
  type Space,
  type TimedNote,
  type TrackState,
} from "../api.ts";
import {
  AttendeesSheet,
  Counter,
  Faces,
  useAttendees,
  type Attendees,
} from "../components/AttendeesSheet.tsx";
import { LiveWave } from "../components/LiveWave.tsx";
import { LevelMeter } from "../components/LevelMeter.tsx";
import { MicsControl } from "../components/MicsControl.tsx";
import { keepStopProblem } from "../stopNotice.ts";
import { RecordingContext } from "../components/RecordingContext.tsx";
import { formatClock } from "../format.ts";
import { currentMode, type Mode } from "../liveStrip.ts";
import { meterValue } from "../meter.ts";
import { micEvents, microphones, timelineMics } from "../microphones.ts";
import { KIND_LABEL } from "../transcript.ts";
import { recordingKey } from "../recordingKeys.ts";

const OTHER: Record<Mode, Mode> = { scene: "discussion", discussion: "scene" };
const KEY: Record<Mode, string> = { scene: "J", discussion: "D" };

/** While recording (spec §7.2, ADR 0056, D5a): a thin bar (the microphones, the computer's
 *  sound, play or discussion), the alerts over the screen when there are some; at the
 *  centre, that it records, the time, who is there (a number, the names if one wants), its
 *  language and where it goes; then the wave going by, with what is marked on it, and the
 *  three gestures: a key moment, stop, pause. The recording is made by the service:
 *  leaving or closing this page does not stop it. */
export function RecordingPage({
  spaces,
  projects,
  onMoved,
}: {
  spaces: Space[];
  projects: Project[];
  /** Where it goes changed: the side column reads it again. */
  onMoved: () => void;
}) {
  const [state, setState] = useState<RecordingState | null | undefined>(
    undefined,
  );
  const [error, setError] = useState<string | null>(null);
  /** « Arrêter » pressed: paused, stopped in `STOP_DELAY_S` by the service unless taken
   *  back (ADR 0058); when it was pressed, to count down. */
  const [stoppingSince, setStoppingSince] = useState<number | null>(null);
  /** The service's delay before it stops, and whether it was paused before « Arrêter »
   *  (then « Reprendre » leaves it paused). */
  const [stopDelayMs, setStopDelayMs] = useState(3000);
  const pausedBeforeStop = useRef(false);
  const stoppingRef = useRef(false);
  stoppingRef.current = stoppingSince !== null;
  /** Held (paused, or stopping; ADR 0089): the same screen, sharp; its title says it, the
   *  wave stops with what is cut on its head, « Pause » becomes « Reprendre ». */
  const heldRef = useRef(false);
  heldRef.current = state?.state === "paused" || stoppingSince !== null;
  const held =
    Boolean(state) && (state?.state === "paused" || stoppingSince !== null);

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (stoppingSince === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(timer);
  }, [stoppingSince]);
  /** The service no longer answers: the last state shown is not live any more. */
  const [lost, setLost] = useState(false);
  const [note, setNote] = useState("");
  /** Recorded time of the note's first letter: where it belongs. */
  const [noteAt, setNoteAt] = useState<number | null>(null);
  const noteInput = useRef<HTMLInputElement>(null);
  /** « Annoter… » turned into its field (N, or a click). */
  const [annotating, setAnnotating] = useState(false);
  /** « Qui est là ? » open. */
  const [sheet, setSheet] = useState(false);
  /** What was just taken back, offered back for a few seconds (nothing lost to a slip). */
  const [undo, setUndo] = useState<{
    label: string;
    restore: () => Promise<RecordingState>;
  } | null>(null);
  useEffect(() => {
    if (!undo) return;
    const timer = window.setTimeout(() => setUndo(null), 8000);
    return () => window.clearTimeout(timer);
  }, [undo]);
  const latest = useRef<RecordingState | null>(null);
  latest.current = state ?? null;
  const pending = useRef<{ text: string; at: number | null }>({
    text: "",
    at: null,
  });
  pending.current = { text: note, at: noteAt };

  // Leaving the page with a note being typed: it is sent, not abandoned (P8).
  useEffect(
    () => () => {
      const { text, at } = pending.current;
      if (text.trim() && at !== null && latest.current) {
        void fetch("/api/enregistrement/notes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: text.trim(), at_s: at }),
          keepalive: true,
        })
          .then((r) => {
            if (!r.ok) throw new Error(String(r.status));
          })
          .catch(() => {
            // Refused or lost: said on the session's page, with its text (P8).
            const mine = latest.current?.session_id;
            if (mine)
              keepStopProblem(
                mine,
                `Une annotation n'a pas pu être envoyée en quittant l'enregistrement (elle datait de ${formatClock(at)}) : « ${text.trim()} ». Copiez-la dans les notes de la séance.`,
              );
          });
      }
    },
    [],
  );

  useEffect(() => {
    // Left for another page while the stop is awaited: what it said is still kept, but
    // the user is not taken back to the session.
    let cancelled = false;
    api.recording().then(setState, (e: Error) => setError(e.message));
    // The service sends the state ten times a second; the stream ends with the recording.
    const source = new EventSource(api.levelsUrl);
    source.onmessage = (e) => {
      setLost(false);
      setState(JSON.parse(e.data as string) as RecordingState);
    };
    // The browser tries again by itself; meanwhile, it is said.
    source.onerror = () => setLost(true);
    source.addEventListener("fin", () => {
      source.close();
      void (async () => {
        // Stopped (here, from the menu bar, after the delay): to its session, with what
        // the stop said. Waited for as long as it is under way; never left unsaid (P8).
        const mine = latest.current?.session_id ?? null;
        // The page left meanwhile: said on the session's page instead.
        // shortcut: with no session known and the page left, the error goes with the page;
        // the service's journal keeps it.
        const say = (message: string) => {
          if (cancelled && mine) keepStopProblem(mine, message);
          else setError(message);
        };
        const until = Date.now() + 60_000;
        while (Date.now() < until) {
          try {
            const outcome = await api.lastStop();
            if (!outcome.pending) {
              if (outcome.error) {
                // Said on the session's page, where the user is taken all the same.
                if (mine) {
                  keepStopProblem(
                    mine,
                    `L'arrêt a signalé un problème : ${outcome.error}`,
                  );
                  if (!cancelled)
                  window.location.hash = `#/seance/${encodeURIComponent(mine)}`;
                  return;
                }
                say(outcome.error);
                break;
              }
              const stopped = outcome.stopped;
              if (stopped?.session_id === mine && stopped.second_problem)
                keepStopProblem(stopped.session_id, stopped.second_problem);
              if (mine) {
                if (!cancelled)
                  window.location.hash = `#/seance/${encodeURIComponent(mine)}`;
                return;
              }
              break;
            }
          } catch (e) {
            say((e as Error).message);
            break;
          }
          await new Promise((r) => window.setTimeout(r, 200));
        }
        if (Date.now() >= until)
          say(
            "L'arrêt n'a pas répondu à temps. La séance est dans la colonne ; si elle n'y paraît pas arrêtée, quittez puis rouvrez Coulisses.",
          );
        setStoppingSince(null);
        setState(null);
      })();
    });
    return () => {
      cancelled = true;
      source.close();
    };
  }, []);

  /** Runs a request; true if it went through (its refusal is shown, never hidden). */
  const act = useCallback(
    async (step: () => Promise<RecordingState>): Promise<boolean> => {
      try {
        setState(await step());
        setError(null);
        return true;
      } catch (e) {
        setError((e as Error).message);
        return false;
      }
    },
    [],
  );

  const toggle = useCallback(
    () =>
      act(() =>
        // While it stops, « Reprendre » takes the stop back, leaving it as it was: paused
        // if it was paused before « Arrêter » (ADR 0058).
        stoppingRef.current && pausedBeforeStop.current
          ? api.cancelStop()
          : latest.current?.state === "paused"
            ? api.resumeRecording()
            : api.pauseRecording(),
      ).then((done) => {
        if (done) setStoppingSince(null); // taken back: the stop asked is dropped
        return done;
      }),
    [act],
  );
  const mark = useCallback(
    (kind: MarkerKind) => act(() => api.mark(kind)),
    [act],
  );

  const mode = state ? currentMode(state.markers) : null;

  // Where it goes and who is there: read again when the recording changes session.
  const [session, setSession] = useState<Session | null>(null);
  const sessionId = state?.session_id ?? null;
  useEffect(() => {
    if (!sessionId) return;
    api.session(sessionId).then(
      (detail) => setSession(detail.session),
      (e: Error) => setError(e.message),
    );
  }, [sessionId]);
  const [people, setPeople] = useState<Person[] | null>(null);
  const spaceId = session?.space_id ?? null;
  const loadPeople = useCallback(async () => {
    if (spaceId === null) return;
    try {
      setPeople((await api.people(spaceId)).filter((p) => !p.archived));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [spaceId]);
  useEffect(() => {
    setPeople(null);
    void loadPeople();
  }, [loadPeople]);
  const attendees = useAttendees(session, setSession, setError);

  // Space: pause or resume. J, D: play or discussion. M: a key moment. N: write a note.
  // In a field or a list, keys keep their own meaning (rules/web.md); on a button just
  // clicked, they still work, and Space pauses rather than pressing it again.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const action = recordingKey(
        e.key.toLowerCase(),
        {
          inField: Boolean(
            target?.closest("input, select, textarea, [contenteditable], [role=dialog]"),
          ),
          onButton: Boolean(target?.closest("button")),
        },
        { held: heldRef.current, stopping: stoppingRef.current },
      );
      if (action === null) return;
      // On a button just clicked, Space pauses rather than pressing it again.
      e.preventDefault();
      if (action === "toggle") void toggle();
      else if (action === "moment") void mark("key_moment");
      else if (action === "annotate") {
        setAnnotating(true);
        noteInput.current?.focus();
      } else if (mode?.mode !== action) void mark(action);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, mark, mode]);

  const saveNote = async () => {
    const text = note.trim();
    if (!text || noteAt === null) return;
    try {
      setState(await api.addTimedNote(text, noteAt));
      setNote("");
      setNoteAt(null);
      setError(null);
    } catch (e) {
      setError((e as Error).message); // the note stays typed, to be sent again
    }
  };

  /** An annotation being typed is sent first: it is never lost to a stop (P8). */
  const sendDraft = async () => {
    if (note.trim() && noteAt !== null) {
      setState(await api.addTimedNote(note.trim(), noteAt));
      setNote("");
      setNoteAt(null);
    }
  };
  /** No confirmation (ADR 0058): paused at once, stopped by the service after a moment
   *  unless taken back; the session's page opens then. */
  const stop = async () => {
    try {
      await sendDraft();
      pausedBeforeStop.current = latest.current?.state === "paused";
      const soon = await api.stopRecordingSoon();
      setState(soon.state);
      setStopDelayMs(soon.delay_s * 1000);
      setStoppingSince(Date.now());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  /** « Arrêter » pressed again while it stops: stopped now; the stream's end then opens
   *  the session, as after the wait. */
  const stopNow = async () => {
    try {
      await sendDraft();
      await api.stopRecordingNow();
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const stopLeft =
    stoppingSince === null
      ? null
      : Math.max(1, Math.ceil((stopDelayMs - (now - stoppingSince)) / 1000));

  const paused = state?.state === "paused";
  const micsCut =
    state && state.extra.length > 0
      ? `${state.extra.length + 1} micros coupés`
      : "Micro coupé";
  const elapsed = state?.elapsed_s ?? 0;
  const mics = state ? microphones(state) : [];

  const system = state?.system ?? null;
  const space = spaces.find((s) => s.id === session?.space_id);

  /** Taken back by its cross, offered back for a few seconds (nothing lost to a slip). */
  const removeMarker = (marker: Marker) =>
    void act(() => api.unmark(marker.id)).then(
      (done) =>
        done &&
        setUndo({
          label: `${marker.kind === "key_moment" ? "Moment clé" : KIND_LABEL[marker.kind]} à ${formatClock(marker.at_s)} retiré`,
          restore: () => api.mark(marker.kind, marker.at_s),
        }),
    );
  const removeNote = (taken: TimedNote) =>
    void act(() => api.removeTimedNote(taken.id)).then(
      (done) =>
        done &&
        setUndo({
          label: `Annotation de ${formatClock(taken.at_s)} retirée`,
          restore: () => api.addTimedNote(taken.text, taken.at_s),
        }),
    );

  return (
    <div className="cl-page cl-rec">
      {state === null && (
        <main className="cl-rec__none">
          <Heading level={2}>Aucun enregistrement en cours</Heading>
          <Text color="secondary">
            Commencez-en un avec « Nouvelle note », en haut à droite (⌘N).
          </Text>
          {note.trim() && (
            <Banner
              status="warning"
              title="Une annotation n'a pas pu être envoyée"
              description={`L'enregistrement s'est arrêté avant son envoi${noteAt !== null ? ` (elle datait de ${formatClock(noteAt)})` : ""} : « ${note.trim()} ». Copiez-la dans les notes de la séance.`}
            />
          )}
        </main>
      )}
      {state && (
        <>
          <header inert={held || undefined} className="cl-rec__bar">
            {/* Held, every microphone is cut (ADR 0059): shown so, the levels flat. */}
            <MicsControl
              mics={held ? mics.map((m) => ({ ...m, muted: true })) : mics}
              act={act}
            />
            {system && (
              <>
                <span className="cl-rec__sep" aria-hidden />
                {/* The computer's sound: its icon and its level are one button (ADR 0056);
                    cut, the icon is crossed and the level greyed and flat. */}
                <button
                  type="button"
                  className="cl-rec__system"
                  data-muted={held || system.muted || undefined}
                  title={
                    system.muted
                      ? "Rétablir le son de l'ordinateur"
                      : "Couper le son de l'ordinateur"
                  }
                  aria-label={
                    system.muted
                      ? "Son de l'ordinateur coupé. Le rétablir"
                      : "Son de l'ordinateur. Le couper"
                  }
                  onClick={(e) => {
                    e.currentTarget.blur();
                    void act(() => api.muteSystem(!system.muted));
                  }}
                >
                  {held || system.muted ? (
                    <MonitorOff size={16} strokeWidth={1.75} aria-hidden />
                  ) : (
                    <Monitor size={16} strokeWidth={1.75} aria-hidden />
                  )}
                  <span className="cl-rec__meter">
                    <LevelMeter
                      level={held || system.muted ? 0 : meterValue(system.levels.rms_db)}
                      peak={held || system.muted ? 0 : meterValue(system.levels.peak_db)}
                      clipping={!held && !system.muted && system.clipping}
                    />
                  </span>
                </button>
              </>
            )}
            <span className="cl-rec__spacer" />
            {mode ? (
              <span className="cl-mode" data-kind={mode.mode}>
                <span className="cl-mode__now">
                  <span className="cl-mode__dot" aria-hidden />
                  {KIND_LABEL[mode.mode]} depuis {formatClock(mode.since)}
                </span>
                <button
                  type="button"
                  className="cl-mode__switch"
                  onClick={(e) => {
                    e.currentTarget.blur();
                    void mark(OTHER[mode.mode]);
                  }}
                >
                  {KIND_LABEL[OTHER[mode.mode]]}
                  <kbd>{KEY[OTHER[mode.mode]]}</kbd>
                </button>
              </span>
            ) : (
              <span className="cl-mode" data-kind="none">
                {(["scene", "discussion"] as const).map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    className="cl-mode__switch"
                    data-kind={kind}
                    onClick={(e) => {
                      e.currentTarget.blur();
                      void mark(kind);
                    }}
                  >
                    {KIND_LABEL[kind]}
                    <kbd>{KEY[kind]}</kbd>
                  </button>
                ))}
              </span>
            )}
          </header>

          {/* Over the screen, under the bar: nothing below moves when one comes. */}
          {/* At the front even when held: what goes wrong is never hidden (P8). */}
          <div
            className="cl-rec__alerts"
            aria-live="polite"
          >
            {lost && (
              <Banner
                status="error"
                title="Connexion au service perdue"
                description="Coulisses ne répond plus : si le service a été arrêté, l'enregistrement a été fermé avec ce qui était enregistré. Rechargez la page quand il est relancé."
              />
            )}
            {error && <Banner status="error" title="Refusé" description={error} />}
            {state.error && (
              <Banner status="error" title="Le micro" description={state.error} />
            )}
            {state.dropouts > 0 && (
              <Banner
                status="warning"
                title="Du son a été perdu"
                description={`Le Mac n'a pas suivi ${state.dropouts === 1 ? "une fois" : `${state.dropouts} fois`} : quelques millisecondes manquent. Fermez les applications lourdes pendant l'enregistrement.`}
              />
            )}
            {state.clipping && (
              <Banner
                status="warning"
                title="Saturation"
                description="Le son est trop fort : éloignez un peu le micro, ou baissez le niveau d'entrée dans Réglages Système, Son."
              />
            )}
            {system?.error && (
              <Banner
                status="warning"
                title="Le son de l'ordinateur"
                description={`${system.error} Le micro continue d'être enregistré.`}
              />
            )}
            {system &&
              !paused &&
              !system.muted &&
              system.too_quiet &&
              !system.error && (
                <Text type="supporting" as="p" className="cl-rec__quiet">
                  Rien du son de l'ordinateur depuis un moment. Si des personnes
                  parlent à distance, autorisez l'audio du système dans Réglages
                  Système, Confidentialité et sécurité, Enregistrement de
                  l'écran et de l'audio du système.
                </Text>
              )}
            {state.extra.map((track) => (
              <ExtraAlerts key={track.device} track={track} />
            ))}
            {state.too_quiet && (
              <Banner
                status="warning"
                title="Niveau très faible"
                description="Presque rien n'arrive depuis un moment : est-ce le bon micro, est-il assez près, et l'accès au micro est-il autorisé (Réglages Système, Confidentialité et sécurité, Micro) ?"
              />
            )}
            {undo && (
              <div className="cl-notice cl-undo" role="status">
                {undo.label}
                <button
                  type="button"
                  className="cl-linkbtn"
                  onClick={() => {
                    const restore = undo.restore;
                    setUndo(null);
                    void act(restore);
                  }}
                >
                  Annuler
                </button>
              </div>
            )}
          </div>

          <main
            className="cl-rec__stage"
            data-held={held || undefined}
            aria-label="Enregistrement"
          >
            <div className="cl-rec__head">
              {held ? (
                <>
                  <span className="cl-rec__status">{formatClock(elapsed)}</span>
                  <h2 className="cl-rec__time" id="cl-rec-held">
                    {stopLeft !== null ? "Arrêt" : "En pause"}
                  </h2>
                </>
              ) : (
                <>
                  <span className="cl-rec__status">
                    <span className="cl-recording__dot" aria-hidden />
                    Enregistrement en cours
                  </span>
                  {/* A width kept for its digits: nothing moves while the time goes by. */}
                  <span
                    className="cl-rec__time"
                    aria-live="off"
                    style={{ minWidth: elapsed >= 3600 ? "7ch" : "5ch" }}
                  >
                    {formatClock(elapsed)}
                  </span>
                </>
              )}
              {session && attendees && people && (
                <div className="cl-rec__who">
                  <Counter attendees={attendees} size="lg" />
                  <Tooltip
                    content={
                      <span className="cl-rec__tip">
                        Dire qui est là
                        <small>{whoSaid(attendees, people)}</small>
                      </span>
                    }
                    placement="below"
                  >
                    <button
                      type="button"
                      className="cl-rec__faces"
                      aria-label={`Dire qui est là : ${whoSaid(attendees, people)}`}
                      onClick={() => setSheet(true)}
                    >
                      <Faces attendees={attendees} people={people} max={6} />
                    </button>
                  </Tooltip>
                </div>
              )}
              {session && (
                <RecordingContext
                  session={session}
                  spaces={spaces}
                  projects={projects}
                  onChanged={(next) => {
                    setSession(next);
                    onMoved();
                  }}
                  onError={setError}
                />
              )}
            </div>

            <div className="cl-rec__wave">
              <LiveWave
                elapsed={elapsed}
                rmsDb={state.levels.rms_db}
                paused={paused}
                markers={state.markers}
                notes={state.notes}
                events={micEvents(timelineMics(state))}
                draftAt={note ? noteAt : null}
                onRemoveMarker={removeMarker}
                onRemoveNote={removeNote}
              />
              {held && (
                // What is cut, on the wave's head (ADR 0089): the microphones, then the
                // computer's sound.
                <span className="cl-rec__cutd" data-at="mics" role="img" aria-label={micsCut}>
                  <MicOff size={22} strokeWidth={1.75} aria-hidden />
                </span>
              )}
              {held && system && (
                <span className="cl-rec__cutd" data-at="system" role="img" aria-label="Son de l'ordinateur coupé">
                  <MonitorOff size={22} strokeWidth={1.75} aria-hidden />
                </span>
              )}
              {annotating || note ? (
                <label className="cl-rec__annotate">
                  {noteAt !== null && note && (
                    <span className="cl-rec__at">{formatClock(noteAt)}</span>
                  )}
                  <input
                    ref={noteInput}
                    type="text"
                    value={note}
                    // As wide as what is typed: its time stays beside it.
                    size={Math.max(note.length + 1, 44)}
                    autoFocus
                    placeholder="Annoter… elle prend l'heure de sa première lettre"
                    aria-label="Annotation horodatée"
                    onBlur={() => {
                      if (!note) setAnnotating(false);
                    }}
                    onChange={(e) => {
                      const typed = e.target.value;
                      if (!note && typed) setNoteAt(latest.current?.elapsed_s ?? 0);
                      if (!typed) setNoteAt(null);
                      setNote(typed);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void saveNote();
                      } else if (e.key === "Escape") {
                        e.currentTarget.blur(); // it stays, to be sent or erased by hand
                      }
                    }}
                  />
                </label>
              ) : (
                <button
                  type="button"
                  className="cl-rec__annotate"
                  onClick={() => setAnnotating(true)}
                >
                  Annoter… <kbd>N</kbd>
                </button>
              )}
            </div>

            <div className="cl-rec__gestures">
              <span className="cl-rec__gesture">
                <button
                  type="button"
                  className="cl-rec__round"
                  aria-label="Marquer un moment"
                  data-kind="moment"
                  disabled={held}
                  onClick={(e) => {
                    e.currentTarget.blur();
                    void mark("key_moment");
                  }}
                >
                  <Star size={20} fill="currentColor" stroke="none" aria-hidden />
                </button>
                <span>
                  Moment<kbd>M</kbd>
                </span>
              </span>
              <span className="cl-rec__gesture">
                <button
                  type="button"
                  className="cl-rec__round"
                  data-kind="stop"
                  aria-label={stopLeft !== null ? "Arrêter tout de suite" : "Arrêter l'enregistrement"}
                  aria-describedby={stopLeft !== null ? "cl-rec-held-desc" : undefined}
                  onClick={(e) => {
                    e.currentTarget.blur();
                    // Pressed again while it stops: stopped now, without the wait (ADR 0089).
                    void (stopLeft !== null ? stopNow() : stop());
                  }}
                >
                  {stopLeft !== null && (
                    // Fills in the service's delay, inside the button; then the session opens.
                    <svg className="cl-rec__ring" aria-hidden width="68" height="68" viewBox="0 0 68 68">
                      <circle cx="34" cy="34" r="28" className="cl-rec__track" />
                      <circle
                        cx="34"
                        cy="34"
                        r="28"
                        className="cl-rec__arc"
                        style={
                          {
                            animationDuration: `${stopDelayMs}ms`,
                            "--cl-rec-steps": Math.max(1, Math.round(stopDelayMs / 1000)),
                          } as React.CSSProperties
                        }
                      />
                    </svg>
                  )}
                  <Square size={22} fill="currentColor" stroke="none" aria-hidden />
                </button>
                {stopLeft !== null && (
                  <span className="cl-sr" id="cl-rec-held-desc">
                    La séance s'ouvre dans un instant.
                  </span>
                )}
                <span className="cl-rec__strong">Arrêter</span>
              </span>
              <span className="cl-rec__gesture">
                <button
                  type="button"
                  className="cl-rec__round"
                  aria-label={paused ? "Reprendre" : "Mettre en pause"}
                  onClick={(e) => {
                    e.currentTarget.blur();
                    void toggle();
                  }}
                >
                  {paused ? (
                    <Play size={20} fill="currentColor" stroke="none" aria-hidden />
                  ) : (
                    <Pause size={20} fill="currentColor" stroke="none" aria-hidden />
                  )}
                </button>
                <span>
                  {paused ? "Reprendre" : "Pause"}
                  <kbd>{stopLeft !== null ? "Échap" : "Espace"}</kbd>
                </span>
              </span>
            </div>
          </main>
          {session && attendees && people && (
            <AttendeesSheet
              isOpen={sheet}
              onClose={() => setSheet(false)}
              session={session}
              spaceName={space?.name ?? "l'espace"}
              people={people}
              attendees={attendees}
              onPeopleChanged={loadPeople}
              onError={setError}
            />
          )}
        </>
      )}
      {!state && error && (
        <Banner status="error" title="Refusé" description={error} />
      )}
    </div>
  );
}

/** Who is named, and how many are not: « Marie, Paul · 2 sans nom ». */
function whoSaid(attendees: Attendees, people: Person[]): string {
  const names = attendees.ids
    .map((id) => people.find((p) => p.id === id)?.name)
    .filter(Boolean)
    .join(", ");
  const unnamed = attendees.count - attendees.ids.length;
  const rest = unnamed > 0 ? `${unnamed} sans nom` : "";
  return [names, rest].filter(Boolean).join(" · ") || "Personne pour l'instant";
}

/** The alerts of a microphone added: it never stops the main recording. */
function ExtraAlerts({ track }: { track: TrackState }) {
  return (
    <>
      {track.error && (
        <Banner
          status="warning"
          title={`Le micro « ${track.device} »`}
          description={`${track.error} L'enregistrement principal continue.`}
        />
      )}
      {track.dropouts > 0 && (
        <Banner
          status="warning"
          title={`« ${track.device} » : du son a été perdu`}
          description={`Le Mac n'a pas suivi ${track.dropouts === 1 ? "une fois" : `${track.dropouts} fois`} sur ce micro : quelques millisecondes y manquent.`}
        />
      )}
      {!track.error && track.too_quiet && (
        <Banner
          status="warning"
          title={`« ${track.device} » : niveau très faible`}
          description="Presque rien n'arrive de ce micro : s'il s'agit d'un téléphone, est-il toujours près du Mac, et son micro libre ?"
        />
      )}
    </>
  );
}
