import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog } from "@astryxdesign/core/Dialog";
import { Text } from "@astryxdesign/core/Text";
import { api, type ModelAction, type ModelsView } from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { gigabytes, percent } from "../models.ts";
import { Onboarding } from "./Onboarding.tsx";

import {
  onStepsChanged,
  pendingNotices,
  settleReplacements,
  stepsChanged,
  stillAsked,
  takesUpLacking,
  updateNotices,
  lastModelsView,
  type Choice,
  type InstallNotice,
  type Replacing,
  type UpdateNotice,
} from "../steps.ts";
import { basePieces, lineStarted, progressLines } from "../onboarding.ts";
import { MissingDialog } from "./Missing.tsx";
import { ICON, LABELS } from "./pieceWords.ts";

/** The ring's length (r = 20), as in the progress tiles. */
const RING = 2 * Math.PI * 20;
const capital = (text: string) =>
  text.charAt(0).toLocaleUpperCase("fr") + text.slice(1);

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
  /** An update asked from the settings (« Remplacer… »): shown first, even if answered
   *  « later » in this window before. */
  const [asked, setAsked] = useState<string | null>(null);
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
      // Kept for the Transcription tab, which then opens at once (steps.ts); after the kept
      // steps are read, so the dot never counts one kept for good.
      stepsChanged(models);
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
    const { ready, left } = settleReplacements(
      replacing.current,
      view,
      actions,
    );
    replacing.current = left;
    if (!ready.length) return;
    void (async () => {
      try {
        for (const key of ready.flatMap((r) => r.remove))
          await api.removeModel(key);
      } catch (e) {
        setFailed(
          `Le nouveau modèle est installé, mais l'ancien n'a pas pu être supprimé : ${(e as Error).message}`,
        );
        // Never over a recording: then the dot on « Réglages » and the next opening say it.
        const recording = await api.recording().catch(() => "unknown" as const);
        if (recording === null && !onRecordingPage.current) setOpen(true);
      }
      try {
        await reload();
      } catch (e) {
        // The service gone: the frame says it.
        console.warn(
          "updates: reading the models again:",
          (e as Error).message,
        );
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
            before: actions
              .filter(
                (a) => a.kind === "model" && notice.download.includes(a.name),
              )
              .map((a) => a.started_at),
          },
        ];
      let refused: unknown = null;
      try {
        if (choice.kind === "removeOld")
          for (const key of notice.remove) await api.removeModel(key);
        if (choice.kind === "removeEnvironments")
          for (const path of notice.removeEnvironments)
            await api.removeEnvironment(path);
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
        console.warn(
          "updates: reading the models again:",
          (e as Error).message,
        );
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
    asked,
    /** Opens the window on this update. */
    openOn: useCallback((id: string) => {
      setAsked(id);
      setOpen(true);
    }, []),
    clearAsked: useCallback(() => setAsked(null), []),
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
  asked = null,
  onAskedAnswered,
  actions,
  failed,
  onChoose,
  onStop,
  onClose,
  onFailedRead,
}: {
  isOpen: boolean;
  notices: UpdateNotice[];
  /** The one asked from the settings: shown first, even if passed before. */
  asked?: string | null;
  /** The asked one was answered: it follows the usual rule again. */
  onAskedAnswered?: () => void;
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
  /** « Ce qui manque » closed: « later » for this session, whatever lacks by then. */
  const [lackingLater, setLackingLater] = useState(false);
  const queue = stillAsked(notices, passed, asked, lackingLater).filter(
    (n) => !(working && sameUpdate(n, working)),
  );
  const shown = working ?? queue[0] ?? null;
  const next = queue[0] ?? null;

  // The first launch: its own steps (ADR 0079), kept until closed, even once what it
  // downloads is there and the update itself is gone.
  const [welcoming, setWelcoming] = useState(false);
  const welcome = shown?.kind === "install" && shown.welcome;
  useEffect(() => {
    if (isOpen && welcome) setWelcoming(true);
  }, [isOpen, welcome]);
  // Later, what the processing lacks: the « Ce qui manque » window (ADR 0079), kept until
  // closed, even once it is all there.
  const [lacking, setLacking] = useState<InstallNotice | null>(null);
  useEffect(() => {
    if (takesUpLacking(isOpen, shown, welcoming, lackingLater))
      setLacking((current) => current ?? (shown as InstallNotice));
  }, [isOpen, shown, welcoming, lackingLater]);

  // A removal that failed after a replacement: back to the choices, the error said.
  useEffect(() => {
    if (failed) setWorking(null);
  }, [failed]);
  // Every update answered: the window has nothing more to say.
  useEffect(() => {
    if (isOpen && shown === null && passed.length) onClose();
  }, [isOpen, shown, passed.length, onClose]);

  if (welcoming || (isOpen && welcome))
    return (
      <Onboarding
        isOpen={isOpen}
        actions={actions}
        onClose={() => {
          // Closed: everything waits for the next launch. What still downloads goes on,
          // followed in Réglages › Transcription; no other window opens behind it.
          setWelcoming(false);
          setLackingLater(true);
          setLacking(null);
          onClose();
        }}
      />
    );
  const view = lastModelsView();
  if (lacking && view && isOpen)
    return (
      <MissingDialog
        view={view}
        pieces={basePieces(view)}
        chosen={[]}
        startedAlready={progressLines(basePieces(view), [], LABELS).some(
          (line) => lineStarted(line, actions),
        )}
        onStarted={() =>
          void api
            .engineModels()
            .then(stepsChanged)
            .catch((e: Error) =>
              // The service gone: the frame says it; the window follows the downloads.
              console.warn("updates: reading the models again:", e.message),
            )
        }
        onClose={() => {
          // Closed: « later », asked again at the next launch.
          setLackingLater(true);
          setLacking(null);
          if (!queue.some((n) => n.kind !== "install")) onClose();
        }}
      />
    );
  if (!shown || shown.kind === "install") return null;

  const pick = async (choice: Choice) => {
    setChoosing(true);
    setRefused(null);
    try {
      await onChoose(shown, choice);
      setPassed((ids) => [...ids, shown.id]);
      if (shown.id === asked) onAskedAnswered?.();
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
  const stopped = actions.filter(
    (a) => own(a) && (a.state === "failed" || a.state === "cancelled"),
  );
  const done = working !== null && live === null && running.length === 0;
  const error = failed ?? refused;

  const [primary, other] = [...shown.choices].sort(
    (a, b) => Number(b.recommended) - Number(a.recommended),
  );
  const progressOf = (key: string) =>
    actions.find(
      (a) => a.kind === "model" && a.name === key && a.state === "running",
    ) ?? null;

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => !open && onClose()}
      width={560}
      aria-label={shown.title}
    >
      {/* The same window as the onboarding and « Ce qui manque » (ADR 0079): a title,
          tiles, the buttons at the bottom; it keeps its size from the choice to the end. */}
      <div className="cl-onb cl-update">
        <h2 className="cl-onb__title">
          {working === null
            ? shown.title
            : done
              ? "C'est fait"
              : shown.kind === "replacement" && shown.download.length
                ? "Remplacement en cours"
                : "C'est en cours"}
        </h2>
        {error && (
          <Banner
            status="error"
            title="Ce n'est pas fini"
            description={error}
            isDismissable
            onDismiss={() => (failed ? onFailedRead() : setRefused(null))}
          />
        )}
        {working === null && <p className="cl-onb__text">{shown.explanation}</p>}
        <div
          className="cl-update__tiles"
          data-swap={shown.kind === "replacement" && shown.tiles.length === 2 || undefined}
        >
          {shown.tiles.map((tile, i) => {
            const Icon = ICON[tile.piece];
            const running = working !== null && tile.role === "new" ? progressOf(tile.key) : null;
            const measured = running ? percent(running) : null;
            const halted =
              working !== null && tile.role === "new"
                ? (stopped.find((a) => a.kind === "model" && a.name === tile.key) ?? null)
                : null;
            const share = done ? 100 : (measured ?? 0);
            return (
              <Fragment key={tile.key}>
                {i > 0 && shown.kind === "replacement" && (
                  <span className="cl-update__arrow" aria-hidden>
                    <ArrowRight size={20} strokeWidth={2} />
                  </span>
                )}
                <div className="cl-onb__tile" data-old={tile.role === "old" || undefined}>
                  {working !== null && tile.role === "new" ? (
                    <span className="cl-ring" data-done={done || undefined}>
                      <svg viewBox="0 0 44 44" aria-hidden>
                        <circle className="cl-ring__track" cx="22" cy="22" r="20" />
                        <circle
                          className="cl-ring__value"
                          cx="22"
                          cy="22"
                          r="20"
                          style={{
                            strokeDasharray: RING,
                            strokeDashoffset: RING * (1 - share / 100),
                          }}
                        />
                      </svg>
                      <span className="cl-ring__icon">
                        {done ? (
                          <Check size={16} strokeWidth={2.5} aria-hidden />
                        ) : (
                          <Icon size={18} strokeWidth={1.75} aria-hidden />
                        )}
                      </span>
                    </span>
                  ) : (
                    <span className="cl-onb__icon">
                      <Icon size={20} strokeWidth={1.75} aria-hidden />
                    </span>
                  )}
                  <span className="cl-onb__name">{tile.name}</span>
                  <span className="cl-onb__what">{tile.what}</span>
                  {working === null ? (
                    <span className="cl-onb__size">
                      {tile.bytes === null ? "" : gigabytes(tile.bytes)}
                    </span>
                  ) : (
                    <div className="cl-missing__foot">
                      <div className="cl-missing__row">
                        {running ? (
                          <button
                            type="button"
                            className="cl-linkbtn cl-missing__act"
                            onClick={() => void onStop(running)}
                          >
                            Arrêter
                          </button>
                        ) : (
                          <span />
                        )}
                        <span className="cl-onb__pct">
                          {tile.role === "new"
                            ? done
                              ? "Prêt"
                              : running
                                ? measured === null
                                  ? "En cours"
                                  : `${measured} %`
                                : halted
                                  ? halted.state === "failed"
                                    ? "Échoué"
                                    : "Arrêté"
                                  : "En attente"
                            : done
                              ? "Supprimé"
                              : "En attente"}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </Fragment>
            );
          })}
        </div>
        {working === null && shown.gains.length > 0 && (
          <dl className="cl-update__gains">
            {shown.gains.map((gain) => (
              <div key={gain.label}>
                <dd>{capital(gain.value)}</dd>
                <dt>{gain.label}</dt>
              </div>
            ))}
          </dl>
        )}
        {working === null && shown.note && (
          <p className="cl-onb__text">{shown.note}</p>
        )}
        {dev && working === null && (shown.evidence || shown.tiles.length) && (
          <Text type="supporting">
            {[shown.evidence, shown.tiles.map((t) => t.key).join(", ")]
              .filter(Boolean)
              .join(" · ")}
          </Text>
        )}
        {working !== null && !done && running.length > 0 && (
          <p className="cl-onb__text">
            Vous pouvez fermer cette fenêtre : le remplacement continue.
          </p>
        )}
        {stopped.map((action) => (
          <p key={`${action.kind}:${action.name}`} className="cl-onb__failed">
            {action.error}
            {dev && action.detail ? ` (${action.detail})` : ""}
          </p>
        ))}
        {working === null ? (
          <div className="cl-onb__actions cl-onb__actions--end">
            <div className="cl-onb__right">
              <Button
                label={other.label}
                variant="ghost"
                isDisabled={choosing}
                onClick={() => void pick(other)}
              />
              <Button
                label={primary.label}
                variant="primary"
                isLoading={choosing}
                onClick={() => void pick(primary)}
              />
            </div>
          </div>
        ) : (
          <div className="cl-onb__actions cl-onb__actions--end">
            <div className="cl-onb__right">
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
                variant="primary"
                onClick={() => (next ? setWorking(null) : onClose())}
              />
            </div>
          </div>
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
