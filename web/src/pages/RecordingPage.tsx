import { useCallback, useEffect, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { ArrowLeft, Pause, Play, Square } from "lucide-react";
import { api, type RecordingState } from "../api.ts";
import { RecordingVisual } from "../components/RecordingVisual.tsx";
import { formatClock } from "../format.ts";
import { meterValue } from "../meter.ts";

/** While recording (spec §7.2): the time, the level, the alerts, pause and stop. The
 *  recording is made by the service: leaving or closing this page does not stop it. */
export function RecordingPage() {
  const [state, setState] = useState<RecordingState | null | undefined>(
    undefined,
  );
  const [error, setError] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  /** The service no longer answers: the last state shown is not live any more. */
  const [lost, setLost] = useState(false);

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

  const toggle = useCallback(async () => {
    if (!state) return;
    try {
      setState(
        await (state.state === "paused"
          ? api.resumeRecording()
          : api.pauseRecording()),
      );
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [state]);

  // Space pauses and resumes, as on the player.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      // On a button, a field or a list, Space keeps its own meaning (rules/web.md).
      if (
        e.key !== " " ||
        confirmStop ||
        target?.closest("button, input, select, textarea, [contenteditable]")
      )
        return;
      e.preventDefault();
      void toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, confirmStop]);

  const stop = async () => {
    try {
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
          </div>
        )}
        {state && (
          <>
            <p className="cl-recording__status" data-paused={paused || undefined}>
              <span className="cl-recording__dot" aria-hidden />
              {paused ? "En pause" : "Enregistrement"} · {state.device}
            </p>
            <RecordingVisual niveau={level} pause={paused} />
            <p className="cl-recording__time" aria-live="off">
              {formatClock(state.elapsed_s)}
            </p>
            <div
              className="cl-meter"
              role="meter"
              aria-label="Niveau d'entrée"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={level}
              data-clipping={state.clipping || undefined}
            >
              <span
                className="cl-meter__level"
                style={{ width: `${level}%` }}
              />
              <span className="cl-meter__peak" style={{ left: `${peak}%` }} />
            </div>
            <div className="cl-recording__alerts" aria-live="polite">
              {lost && (
                <Banner
                  status="error"
                  title="Connexion au service perdue"
                  description="Coulisses ne répond plus : si le service a été arrêté, l'enregistrement a été fermé avec ce qui était enregistré. Rechargez la page quand il est relancé."
                />
              )}
              {state.dropouts > 0 && (
                <Banner
                  status="warning"
                  title="Du son a été perdu"
                  description={`Le Mac n'a pas suivi ${state.dropouts === 1 ? "une fois" : `${state.dropouts} fois`} : quelques millisecondes manquent. Fermez les applications lourdes pendant l'enregistrement.`}
                />
              )}
              {state.error && (
                <Banner
                  status="error"
                  title="Le micro"
                  description={state.error}
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
                clickAction={toggle}
              />
              <Button
                label="Arrêter"
                variant="primary"
                icon={<Square size={14} strokeWidth={1.75} />}
                onClick={() => setConfirmStop(true)}
              />
            </div>
            <Text type="supporting" as="p">
              Espace : pause ou reprise. Vous pouvez quitter cette page :
              l'enregistrement continue.
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
