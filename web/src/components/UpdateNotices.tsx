import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog } from "@astryxdesign/core/Dialog";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Text } from "@astryxdesign/core/Text";
import { api, type ModelAction, type ModelsView } from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { gigabytes, percent } from "../models.ts";
import {
  onStepsChanged,
  pendingNotices,
  settleReplacements,
  stepsChanged,
  updateNotices,
  type Choice,
  type Replacing,
  type UpdateNotice,
} from "../steps.ts";

/** The updates the engine's state asks about (ADR 0049): read once at launch, kept up to
 *  date by whoever reads the models' view again. `open`: the window, opened at launch when
 *  one is left that was not kept for good, never while recording. What the user chose is
 *  done here, the window open or not: a download is followed, and a replaced model removed
 *  once its successor is installed. */
export function useUpdateNotices(recordingPage: boolean) {
  const [view, setView] = useState<ModelsView | null>(null);
  const [actions, setActions] = useState<ModelAction[]>([]);
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  /** A removal that could not be done after a replacement: said in the window, which
   *  opens again for it if it was closed (P8). */
  const [failed, setFailed] = useState<string | null>(null);
  const replacing = useRef<Replacing[]>([]);
  const onRecordingPage = useRef(recordingPage);
  onRecordingPage.current = recordingPage;

  useEffect(
    () =>
      onStepsChanged((next) => {
        setView(next);
        setActions(next.actions);
      }),
    [],
  );
  useEffect(() => {
    let gone = false;
    void (async () => {
      let models: ModelsView;
      try {
        models = await api.engineModels();
      } catch (e) {
        // Said in the settings, where the models are read again.
        console.warn(
          "updates: the models could not be read:",
          (e as Error).message,
        );
        return;
      }
      // Each read on its own: one that fails does not hide the updates.
      const kept = await api.dismissedSteps().catch((e: Error) => {
        console.warn(
          "updates: the ones kept for good could not be read:",
          e.message,
        );
        return [] as string[];
      });
      const recording = await api.recording().catch(() => "unknown" as const);
      if (gone) return;
      setView(models);
      setActions(models.actions);
      setDismissed(kept);
      const left = pendingNotices(updateNotices(models), kept);
      if (left.length && recording === null && !onRecordingPage.current)
        setOpen(true);
    })();
    return () => {
      gone = true;
    };
  }, []);

  const reload = useCallback(async () => {
    stepsChanged(await api.engineModels());
  }, []);
  const refreshActions = useCallback(async () => {
    setActions(await api.modelActions());
  }, []);

  // While something downloads or installs: its progress, twice a second; the view again
  // once it ends (what is on the disk changed).
  const busy = actions.some((a) => a.state === "running");
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.modelActions();
        const ended = actions.some(
          (a) =>
            a.state === "running" &&
            !next.some(
              (n) =>
                n.kind === a.kind && n.name === a.name && n.state === "running",
            ),
        );
        setActions(next);
        if (ended) await reload();
      } catch (e) {
        // The service gone: the frame says it; the next tick tries again.
        console.warn("updates: following the downloads:", (e as Error).message);
      }
    }, 500);
    return () => window.clearInterval(timer);
  }, [busy, actions, reload]);

  // A replacement: the old model goes once the new one is installed; if its download
  // failed or was stopped, nothing is removed (the window offers the choice again).
  useEffect(() => {
    if (!view || !replacing.current.length) return;
    const { ready, left } = settleReplacements(replacing.current, view, actions);
    replacing.current = left;
    if (!ready.length) return;
    void (async () => {
      try {
        for (const key of ready.flatMap((r) => r.remove)) await api.removeModel(key);
      } catch (e) {
        setFailed(`Le nouveau modèle est installé, mais l'ancien n'a pas pu être supprimé : ${(e as Error).message}`);
        // Never over a recording: then the dot on « Réglages » and the next opening say it.
        const recording = await api.recording().catch(() => "unknown" as const);
        if (recording === null && !onRecordingPage.current) setOpen(true);
      }
      try {
        await reload();
      } catch (e) {
        // The service gone: the frame says it.
        console.warn("updates: reading the models again:", (e as Error).message);
      }
    })();
  }, [view, actions, reload]);

  /** What the user chose, done: each action asked of the service; a refusal is thrown, to
   *  be said in the window. */
  const choose = useCallback(
    async (notice: UpdateNotice, choice: Choice) => {
      const drop = () => {
        replacing.current = replacing.current.filter((r) => r.id !== notice.id);
      };
      if (choice.kind === "later") return drop();
      if (choice.kind === "keep") {
        drop();
        setDismissed(await api.dismissSteps([notice.id]));
        return;
      }
      if (choice.kind === "replace")
        replacing.current = [
          ...replacing.current,
          {
            id: notice.id,
            remove: notice.remove,
            when: notice.download,
            // What ended before this choice says nothing about it.
            before: actions.filter((a) => a.kind === "model" && notice.download.includes(a.name)).map((a) => a.started_at),
          },
        ];
      let refused: unknown = null;
      try {
        if (choice.kind === "removeOld") for (const key of notice.remove) await api.removeModel(key);
        if (choice.kind === "removeEnvironments")
          for (const path of notice.removeEnvironments) await api.removeEnvironment(path);
        for (const key of notice.download) await api.downloadModel(key);
        for (const name of notice.install) await api.installEnvironment(name);
      } catch (e) {
        drop();
        refused = e;
      }
      try {
        await refreshActions();
        await reload();
      } catch (e) {
        // The service gone: the frame says it; what was asked runs on.
        console.warn("updates: reading the models again:", (e as Error).message);
      }
      if (refused) throw refused;
    },
    [actions, refreshActions, reload],
  );

  /** A download or an install stopped from the window (it resumes next time). */
  const stop = useCallback(
    async (action: ModelAction) => {
      await api.cancelModelAction(action.kind, action.name);
      await refreshActions();
    },
    [refreshActions],
  );

  const notices = view ? pendingNotices(updateNotices(view), dismissed) : [];
  return {
    notices,
    actions,
    open,
    setOpen,
    choose,
    stop,
    failed,
    clearFailed: useCallback(() => setFailed(null), []),
  };
}

/** The window: one update at a time, light: its nature, one sentence, a few figures, then
 *  its two ways out, the recommended one first. Each way out says what it does before it
 *  is done (the network, the space freed): choosing it is the user's explicit decision
 *  (P1, P8). Closing it (Escape) is « later ». */
export function UpdateNoticesDialog({
  isOpen,
  notices,
  actions,
  failed,
  onChoose,
  onStop,
  onClose,
  onFailedRead,
}: {
  isOpen: boolean;
  notices: UpdateNotice[];
  actions: ModelAction[];
  failed: string | null;
  onChoose: (notice: UpdateNotice, choice: Choice) => Promise<void>;
  onStop: (action: ModelAction) => Promise<void>;
  onClose: () => void;
  onFailedRead: () => void;
}) {
  const dev = useDevMode();
  /** The updates answered in this window, in order. */
  const [passed, setPassed] = useState<string[]>([]);
  /** The one whose way out is being done: followed until it is. */
  const [working, setWorking] = useState<UpdateNotice | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  // The one being done stays the same while it changes form (a replacement whose new
  // model is installed, its old one being removed).
  const queue = notices.filter((n) => !passed.includes(n.id) && !(working && sameUpdate(n, working)));
  const shown = working ?? queue[0] ?? null;
  const next = queue[0] ?? null;

  // A removal that failed after a replacement: back to the choices, the error said.
  useEffect(() => {
    if (failed) setWorking(null);
  }, [failed]);
  // Every update answered: the window has nothing more to say.
  useEffect(() => {
    if (isOpen && shown === null && passed.length) onClose();
  }, [isOpen, shown, passed.length, onClose]);

  if (!shown) return null;

  const pick = async (choice: Choice) => {
    setChoosing(true);
    setRefused(null);
    try {
      await onChoose(shown, choice);
      setPassed((ids) => [...ids, shown.id]);
      if (choice.kind !== "later" && choice.kind !== "keep") setWorking(shown);
    } catch (e) {
      setRefused((e as Error).message);
    } finally {
      setChoosing(false);
    }
  };

  // Being done: what runs for it, what stopped, whether it is over.
  const live = notices.find((n) => sameUpdate(n, shown)) ?? null;
  const own = (a: ModelAction) =>
    (a.kind === "model" && shown.download.includes(a.name)) ||
    (a.kind === "environment" && shown.install.includes(a.name));
  const running = actions.filter((a) => own(a) && a.state === "running");
  const stopped = actions.filter((a) => own(a) && (a.state === "failed" || a.state === "cancelled"));
  const done = working !== null && live === null && running.length === 0;
  const error = failed ?? refused;

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => !open && onClose()}
      width={480}
      aria-label={`${shown.eyebrow} : ${shown.title}`}
    >
      <div className="cl-update">
        <Text type="supporting" color="secondary">
          {shown.eyebrow}
        </Text>
        <h2 className="cl-update__title">{working === null ? shown.title : done ? "C'est fait" : "C'est en cours"}</h2>
        {error && (
          <Banner
            status="error"
            title="Ce n'est pas fini"
            description={error}
            isDismissable
            onDismiss={() => (failed ? onFailedRead() : setRefused(null))}
          />
        )}
        {working === null ? (
          <>
            <Text as="p" color="secondary">
              {shown.explanation}
            </Text>
            {shown.gains.length > 0 && (
              <dl className="cl-gains">
                {shown.gains.map((gain) => (
                  <div key={gain.label} className="cl-gains__item">
                    <dt>{gain.label}</dt>
                    <dd>{gain.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {shown.note && <Text type="supporting">{shown.note}</Text>}
            {dev && (
              <Text type="supporting">
                {[shown.evidence, [...shown.download, ...shown.install, ...shown.remove].join(", ")]
                  .filter(Boolean)
                  .join(" · ")}
              </Text>
            )}
            <div className="cl-choices">
              {shown.choices.map((choice) => (
                <button
                  key={choice.kind}
                  type="button"
                  className="cl-choice"
                  data-recommended={choice.recommended || undefined}
                  disabled={choosing}
                  onClick={() => void pick(choice)}
                >
                  <span className="cl-choice__label">
                    {choice.label}
                    {choice.recommended ? " (recommandé)" : ""}
                  </span>
                  <span className="cl-choice__description">{choice.description}</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            {!done && running.length > 0 && (
              <Text as="p" color="secondary">
                {shown.kind === "replacement"
                  ? "Le nouveau modèle se télécharge. L'ancien sera supprimé ensuite. Vous pouvez fermer cette fenêtre."
                  : "Le téléchargement continue si vous fermez cette fenêtre."}
              </Text>
            )}
            {running.map((action) => {
              const share = percent(action);
              return (
                <div key={`${action.kind}:${action.name}`} className="cl-update__progress">
                  <ProgressBar
                    label={`${gigabytes(action.done_bytes)}${action.total_bytes ? ` sur ${gigabytes(action.total_bytes)}` : ""}`}
                    value={share ?? 0}
                    hasValueLabel={share !== null}
                  />
                  <Button label="Arrêter" size="sm" variant="ghost" onClick={() => void onStop(action)} />
                </div>
              );
            })}
            {stopped.map((action) => (
              <Text key={`${action.kind}:${action.name}`} as="p" color="secondary">
                {action.error}
                {dev && action.detail ? ` (${action.detail})` : ""}
              </Text>
            ))}
            <div className="cl-update__buttons">
              {stopped.length > 0 && running.length === 0 && (
                <Button
                  label="Revenir aux choix"
                  variant="ghost"
                  onClick={() => {
                    setPassed((ids) => ids.filter((id) => id !== shown.id));
                    setWorking(null);
                  }}
                />
              )}
              <Button
                label={next ? "Suivant" : "Fermer"}
                variant={done ? "primary" : "secondary"}
                onClick={() => (next ? setWorking(null) : onClose())}
              />
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}

/** The same update, whatever its form: a replacement by its old model, a cleanup or an
 *  install by its id. */
function sameUpdate(a: UpdateNotice, b: UpdateNotice): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "replacement") return a.remove.join() === b.remove.join();
  return a.id === b.id;
}
