import { useCallback, useEffect, useRef, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import {
  ArrowLeft,
  ArrowRight,
  Pause,
  PenLine,
  Play,
  Square,
  Star,
  X,
} from "lucide-react";
import { api, type MarkerKind, type RecordingState } from "../api.ts";
import { LevelMeter } from "../components/LevelMeter.tsx";
import { RecordingVisual } from "../components/RecordingVisual.tsx";
import { formatClock } from "../format.ts";
import { currentMode, liveSegments, type Mode } from "../liveStrip.ts";
import { meterValue } from "../meter.ts";
import { KIND_LABEL } from "../transcript.ts";

const OTHER: Record<Mode, Mode> = { scene: "discussion", discussion: "scene" };
const KEY: Record<Mode, string> = { scene: "J", discussion: "D" };

/** While recording (spec §7.2): the time, the level, the alerts, pause and stop, and what
 *  the group marks as it goes: play or discussion (one switch), a key moment, a note. The
 *  recording is made by the service: leaving or closing this page does not stop it. */
export function RecordingPage() {
  const [state, setState] = useState<RecordingState | null | undefined>(
    undefined,
  );
  const [error, setError] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  /** The service no longer answers: the last state shown is not live any more. */
  const [lost, setLost] = useState(false);
  const [note, setNote] = useState("");
  /** Recorded time of the note's first letter: where it belongs. */
  const [noteAt, setNoteAt] = useState<number | null>(null);
  const noteInput = useRef<HTMLInputElement>(null);
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
  const pending = useRef<{ text: string; at: number | null }>({ text: "", at: null });
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
        }).catch(() => undefined); // the recording ended meanwhile: nothing to attach it to
      }
    },
    [],
  );

  useEffect(() => {
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
      setState(null);
    });
    return () => source.close();
  }, []);

  /** Runs a request; true if it went through (its refusal is shown, never hidden). */
  const act = useCallback(async (step: () => Promise<RecordingState>): Promise<boolean> => {
    try {
      setState(await step());
      setError(null);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  }, []);

  const toggle = useCallback(
    () =>
      act(() =>
        latest.current?.state === "paused"
          ? api.resumeRecording()
          : api.pauseRecording(),
      ),
    [act],
  );
  const mark = useCallback(
    (kind: MarkerKind) => act(() => api.mark(kind)),
    [act],
  );

  const mode = state ? currentMode(state.markers) : null;

  // Space: pause or resume. J, D: play or discussion. M: a key moment. N: write a note.
  // In a field or a list, keys keep their own meaning (rules/web.md); on a button just
  // clicked, they still work, and Space pauses rather than pressing it again.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (confirmStop || e.metaKey || e.ctrlKey || e.altKey) return;
      if (target?.closest("input, select, textarea, [contenteditable]")) return;
      const key = e.key.toLowerCase();
      if (key === " ") void toggle();
      else if (key === "j" && mode?.mode !== "scene") void mark("scene");
      else if (key === "d" && mode?.mode !== "discussion")
        void mark("discussion");
      else if (key === "m") void mark("key_moment");
      else if (key === "n") noteInput.current?.focus();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, mark, mode, confirmStop]);

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

  const stop = async () => {
    try {
      // A note being typed is sent first: it is never lost to the stop (P8).
      if (note.trim() && noteAt !== null) {
        setState(await api.addTimedNote(note.trim(), noteAt));
        setNote("");
        setNoteAt(null);
      }
      const stopped = await api.stopRecording();
      window.location.hash = `#/seance/${encodeURIComponent(stopped.session_id)}`;
    } catch (e) {
      setError((e as Error).message);
      setConfirmStop(false);
    }
  };

  const paused = state?.state === "paused";
  const level = state ? meterValue(state.levels.rms_db) : 0;
  const peak = state ? meterValue(state.levels.peak_db) : 0;
  const elapsed = state?.elapsed_s ?? 0;
  const segments = state ? liveSegments(state.markers, elapsed) : [];
  const span = Math.max(elapsed, 1);
  const marks = state
    ? [
        ...state.markers.map((m) => ({
          key: `m${m.id}`,
          at: m.at_s,
          marker: m,
          note: null,
        })),
        ...state.notes.map((n) => ({
          key: `n${n.id}`,
          at: n.at_s,
          marker: null,
          note: n,
        })),
      ].sort((a, b) => a.at - b.at)
    : [];

  return (
    <div className="cl-page cl-recording">
      <header className="cl-recording__head">
        <a className="cl-back" href="#/">
          <ArrowLeft size={16} strokeWidth={1.75} aria-hidden /> Enregistrements
        </a>
      </header>
      <main className="cl-recording__main">
        {state === null && (
          <div className="cl-recording__none">
            <Heading level={2}>Aucun enregistrement en cours</Heading>
            <Text color="secondary">
              Lancez-en un depuis la page des enregistrements.
            </Text>
            {note.trim() && (
              <Banner
                status="warning"
                title="Une note n'a pas pu être envoyée"
                description={`L'enregistrement s'est arrêté avant son envoi${noteAt !== null ? ` (elle datait de ${formatClock(noteAt)})` : ""} : « ${note.trim()} ». Copiez-la dans les notes de la séance.`}
              />
            )}
          </div>
        )}
        {state && (
          <>
            <section className="cl-recording__top">
              <RecordingVisual niveau={level} pause={paused} />
              <div className="cl-recording__clock">
                <p
                  className="cl-recording__status"
                  data-paused={paused || undefined}
                >
                  <span className="cl-recording__dot" aria-hidden />
                  {paused ? "En pause" : "Enregistrement"} · {state.device}
                </p>
                <p className="cl-recording__time" aria-live="off">
                  {formatClock(elapsed)}
                </p>
                <LevelMeter level={level} peak={peak} clipping={state.clipping} />
                <div className="cl-recording__controls">
                  <Button
                    label={paused ? "Reprendre" : "Pause"}
                    icon={
                      paused ? (
                        <Play size={16} strokeWidth={1.75} />
                      ) : (
                        <Pause size={16} strokeWidth={1.75} />
                      )
                    }
                    clickAction={async () => void (await toggle())}
                  />
                  <Button
                    label="Arrêter"
                    variant="primary"
                    icon={<Square size={14} strokeWidth={1.75} />}
                    onClick={() => setConfirmStop(true)}
                  />
                </div>
              </div>
            </section>

            <div className="cl-recording__alerts" aria-live="polite">
              {lost && (
                <Banner
                  status="error"
                  title="Connexion au service perdue"
                  description="Coulisses ne répond plus : si le service a été arrêté, l'enregistrement a été fermé avec ce qui était enregistré. Rechargez la page quand il est relancé."
                />
              )}
              {state.error && (
                <Banner
                  status="error"
                  title="Le micro"
                  description={state.error}
                />
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
              {state.too_quiet && (
                <Banner
                  status="warning"
                  title="Niveau très faible"
                  description="Presque rien n'arrive depuis un moment : est-ce le bon micro, est-il assez près, et l'accès au micro est-il autorisé (Réglages Système, Confidentialité et sécurité, Micro) ?"
                />
              )}
            </div>

            <section className="cl-live" aria-label="Déroulé de la séance">
              <div className="cl-live__bar">
                {segments.map((s) => (
                  <span
                    key={`${s.kind}${s.start}`}
                    className="cl-live__segment"
                    data-kind={s.kind}
                    style={{
                      left: `${(s.start / span) * 100}%`,
                      width: `${((s.end - s.start) / span) * 100}%`,
                    }}
                  />
                ))}
                {state.markers
                  .filter((m) => m.kind === "key_moment")
                  .map((m) => (
                    <span
                      key={m.id}
                      className="cl-live__moment"
                      style={{ left: `${(m.at_s / span) * 100}%` }}
                      title={`Moment clé à ${formatClock(m.at_s)}`}
                    />
                  ))}
              </div>

              <div className="cl-live__actions">
                {mode ? (
                  <div className="cl-mode" data-kind={mode.mode}>
                    <span className="cl-mode__now">
                      <span className="cl-mode__dot" aria-hidden />
                      {KIND_LABEL[mode.mode]}
                      <span className="cl-mode__since">
                        depuis {formatClock(mode.since)}
                      </span>
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
                      <ArrowRight size={14} strokeWidth={1.75} aria-hidden />
                      <kbd>{KEY[OTHER[mode.mode]]}</kbd>
                    </button>
                  </div>
                ) : (
                  <div className="cl-mode" data-kind="none">
                    <span className="cl-mode__ask">On commence par…</span>
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
                  </div>
                )}
                <button
                  type="button"
                  className="cl-moment"
                  onClick={(e) => {
                    e.currentTarget.blur();
                    void mark("key_moment");
                  }}
                  title="Marquer ce moment (M)"
                >
                  <Star size={16} strokeWidth={1.75} aria-hidden />
                  Moment
                  <kbd>M</kbd>
                </button>
              </div>

              <label className="cl-livenote">
                <PenLine size={16} strokeWidth={1.75} aria-hidden />
                <input
                  ref={noteInput}
                  type="text"
                  value={note}
                  placeholder="Une note… elle prend l'heure de sa première lettre"
                  aria-label="Note horodatée"
                  onChange={(e) => {
                    const typed = e.target.value;
                    if (!note && typed)
                      setNoteAt(latest.current?.elapsed_s ?? 0);
                    if (!typed) setNoteAt(null);
                    setNote(typed);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void saveNote();
                    } else if (e.key === "Escape") {
                      e.currentTarget.blur(); // the note stays, to be sent or erased by hand
                    }
                  }}
                />
                {noteAt !== null && note && (
                  <span className="cl-livenote__at">
                    à {formatClock(noteAt)}
                  </span>
                )}
              </label>

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
              {marks.length > 0 && (
                <ol className="cl-marks">
                  {marks.map((item) => (
                    <li key={item.key} data-kind={item.marker?.kind ?? "note"}>
                      <span className="cl-marks__time">
                        {formatClock(item.at)}
                      </span>
                      <span className="cl-marks__what">
                        {item.marker ? (
                          item.marker.kind === "key_moment" ? (
                            <>
                              <Star size={13} strokeWidth={1.75} aria-hidden />{" "}
                              Moment clé
                            </>
                          ) : (
                            <>
                              <span className="cl-mode__dot" aria-hidden />{" "}
                              {KIND_LABEL[item.marker.kind]}
                            </>
                          )
                        ) : (
                          <>
                            <PenLine size={13} strokeWidth={1.75} aria-hidden />{" "}
                            {item.note?.text}
                          </>
                        )}
                      </span>
                      <button
                        type="button"
                        className="cl-marks__remove"
                        aria-label="Retirer"
                        title="Retirer"
                        onClick={(e) => {
                          e.currentTarget.blur();
                          const marker = item.marker;
                          const taken = item.note;
                          void act(() =>
                            marker ? api.unmark(marker.id) : api.removeTimedNote(taken!.id),
                          ).then((done) =>
                            done && setUndo(
                              marker
                                ? {
                                    label: `${marker.kind === "key_moment" ? "Moment clé" : KIND_LABEL[marker.kind]} à ${formatClock(marker.at_s)} retiré`,
                                    restore: () => api.mark(marker.kind, marker.at_s),
                                  }
                                : {
                                    label: `Note de ${formatClock(taken!.at_s)} retirée`,
                                    restore: () => api.addTimedNote(taken!.text, taken!.at_s),
                                  },
                            ),
                          );
                        }}
                      >
                        <X size={13} strokeWidth={1.75} />
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </section>

            <Text type="supporting" as="p">
              Espace : pause. J, D : jeu ou discussion. M : moment clé. N : une
              note. Vous pouvez quitter cette page : l'enregistrement continue.
            </Text>
          </>
        )}
        {error && <Banner status="error" title="Refusé" description={error} />}
      </main>
      <AlertDialog
        isOpen={confirmStop}
        onOpenChange={(open) => !open && setConfirmStop(false)}
        title="Arrêter l'enregistrement ?"
        description="La séance est enregistrée telle quelle. Son traitement démarre tout de suite si le Mac est branché ; sur batterie, vous le lancerez quand vous voudrez."
        actionLabel="Arrêter"
        cancelLabel="Continuer"
        onAction={stop}
      />
    </div>
  );
}
