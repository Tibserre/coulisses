import { useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog } from "@astryxdesign/core/Dialog";
import { Check } from "lucide-react";
import { api, type Language, type ModelAction, type ModelsView } from "../api.ts";
import { gigabytes } from "../models.ts";
import {
  basePieces,
  languageChoices,
  lineRunning,
  lineStarted,
  lineState,
  onboardingDownload,
  progressLines,
  sizeWords,
  toResume,
  type LanguageChoice,
  type Piece,
  type PieceKind,
  type ProgressLine,
} from "../onboarding.ts";
import {
  downloadEverything,
  lastModelsView,
  stepsChanged,
} from "../steps.ts";
import { ICON, LABELS, WHAT } from "./pieceWords.ts";

/** The ring's length (r = 20): its dash offset says what is left. */
const RING = 2 * Math.PI * 20;

const kindOf = (line: ProgressLine): PieceKind =>
  line.key.startsWith("align") ? "align" : (line.key as PieceKind);

/** A session waiting for what this Mac lacks to listen (ADR 0079): the whole page says so,
 *  with one way out, « Voir ce qui manque »: a window with a tile per missing piece and
 *  « Télécharger », then the same tiles filling in. The session starts by itself once all
 *  is there (ADR 0080). Nothing is downloaded without that click (P1). */
export function MissingPage({
  view,
  language,
  languages,
  onStarted,
  said,
  waitingLanguages,
}: {
  view: ModelsView;
  /** The session's language, when not French: its own models come too. */
  language: Language | undefined;
  languages: Language[] | null;
  /** Read again what shows the progress. */
  onStarted: () => void;
  /** What went wrong, said under the page's button (P8). */
  said: string[];
  /** The session's language not read yet: its own models would be left out of the total. */
  waitingLanguages: boolean;
}) {
  const [open, setOpen] = useState(false);
  const pieces = basePieces(view);
  const choices =
    language && languages
      ? languageChoices([language], view.catalog.models)
      : [];
  const lines = progressLines(pieces, choices, LABELS);
  // Only what this session lacks: another download (a language from the settings) does
  // not count.
  const running = lines.some((line) => lineRunning(line, view.actions));
  const started = lines.some((line) => lineStarted(line, view.actions));
  return (
    <section className="cl-missing" aria-label="Il manque de quoi écouter">
      <div className="cl-missing__illus" aria-hidden>
        {(["transcribe", "align", "diarize", "tools"] as const).map((kind) => {
          const Icon = ICON[kind];
          return (
            <span key={kind} className="cl-missing__cell">
              <Icon size={22} strokeWidth={1.75} />
            </span>
          );
        })}
      </div>
      <h2 className="cl-onb__title">
        {running
          ? "Téléchargement en cours"
          : "Il manque de quoi écouter cette séance"}
      </h2>
      <p className="cl-onb__text">
        {running
          ? "La séance partira d'elle-même une fois tout là."
          : "Un téléchargement, une seule fois, et elle sera traitée."}
      </p>
      <Button
        label={running ? "Voir l'avancement" : "Voir ce qui manque"}
        variant="primary"
        isDisabled={waitingLanguages}
        onClick={() => setOpen(true)}
      />
      {said.map((text) => (
        <p key={text} className="cl-onb__error" role="alert">
          {text}
        </p>
      ))}
      {open && (
        <MissingDialog
          view={view}
          pieces={pieces}
          chosen={choices}
          startedAlready={started}
          onStarted={onStarted}
          onClose={() => setOpen(false)}
        />
      )}
    </section>
  );
}

export function MissingDialog({
  view,
  pieces,
  chosen,
  startedAlready,
  onStarted,
  onClose,
}: {
  view: ModelsView;
  pieces: Piece[];
  chosen: LanguageChoice[];
  startedAlready: boolean;
  onStarted: () => void;
  onClose: () => void;
}) {
  const [plan, setPlan] = useState<{
    pieces: Piece[];
    chosen: LanguageChoice[];
  } | null>(startedAlready ? { pieces, chosen } : null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = plan ?? { pieces, chosen };
  const lines = progressLines(shown.pieces, shown.chosen, LABELS);
  const sizeOf = (line: ProgressLine): number | null =>
    line.key.startsWith("align-")
      ? (shown.chosen.find((c) => `align-${c.language.language}` === line.key)
          ?.bytes ?? null)
      : (shown.pieces.find((p) => p.kind === line.key)?.bytes ?? null);
  const total = onboardingDownload(pieces, chosen);

  const reread = async () => {
    try {
      stepsChanged(await api.engineModels());
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const start = async () => {
    setWorking(true);
    setError(null);
    try {
      await downloadEverything(total);
      setPlan({ pieces, chosen });
    } catch (e) {
      setError((e as Error).message);
      // Part of it started: followed here, the refusal said too (P8).
      if ((lastModelsView()?.actions ?? []).some((a) => a.state === "running"))
        setPlan({ pieces, chosen });
    } finally {
      setWorking(false);
      onStarted();
    }
  };
  const act = async (what: () => Promise<unknown>) => {
    setError(null);
    try {
      await what();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      await reread();
      onStarted();
    }
  };

  return (
    <Dialog
      isOpen
      onOpenChange={(isOpen) => !isOpen && onClose()}
      width={560}
      maxHeight="90dvh"
      aria-label={plan ? "Téléchargement en cours" : "Ce qui manque"}
    >
      <div className="cl-onb cl-onb--steps">
        <h2 className="cl-onb__title">
          {plan ? "Téléchargement en cours" : "Ce qui manque"}
        </h2>
        <div className="cl-onb__tiles">
          {lines.map((line) => {
            const Icon = ICON[kindOf(line)];
            if (!plan)
              return (
                <div key={line.key} className="cl-onb__tile">
                  <span className="cl-onb__icon">
                    <Icon size={20} strokeWidth={1.75} aria-hidden />
                  </span>
                  <span className="cl-onb__name">{line.label}</span>
                  <span className="cl-onb__what">{WHAT[kindOf(line)]}</span>
                  <span
                    className="cl-onb__size"
                    data-unknown={sizeOf(line) === null || undefined}
                  >
                    {sizeWords(sizeOf(line), gigabytes)}
                  </span>
                </div>
              );
            return (
              <ProgressTile
                key={line.key}
                line={line}
                view={view}
                actions={view.actions}
                onStop={() =>
                  void act(async () => {
                    for (const a of view.actions.filter(
                      (a) =>
                        a.state === "running" &&
                        (a.kind === "model"
                          ? line.models.includes(a.name)
                          : line.environments.includes(a.name)),
                    ))
                      await api.cancelModelAction(a.kind, a.name);
                  })
                }
                onResume={() =>
                  void act(async () => {
                    const left = toResume(line, view, view.actions);
                    for (const key of left.models) await api.downloadModel(key);
                    for (const name of left.environments)
                      await api.installEnvironment(name);
                  })
                }
              />
            );
          })}
        </div>
        {error && (
          <p className="cl-onb__error" role="alert">
            {error}
          </p>
        )}
        {plan ? (
          <div className="cl-onb__actions">
            <p className="cl-onb__note">
              La séance partira d'elle-même ensuite.
            </p>
            <Button label="Fermer" variant="primary" onClick={onClose} />
          </div>
        ) : (
          <div className="cl-onb__actions cl-onb__actions--end">
            <div className="cl-onb__right">
              <Button label="Plus tard" variant="ghost" onClick={onClose} />
              <Button
                label={`Télécharger · ${total.more ? "plus de " : ""}${gigabytes(total.bytes)}`}
                variant="primary"
                isLoading={working}
                isDisabled={!total.download.length && !total.install.length}
                onClick={() => void start()}
              />
            </div>
          </div>
        )}
      </div>
    </Dialog>
  );
}

/** One piece's progress, as a tile (ADR 0079): the same in the onboarding and in « Ce qui
 *  manque ». « Arrêter » while it runs; « Reprendre » (or « Télécharger ») for what is
 *  neither running nor over. */
export function ProgressTile({
  line,
  view,
  actions,
  onStop,
  onResume,
}: {
  line: ProgressLine;
  view: ModelsView;
  actions: ModelAction[];
  onStop: () => void;
  onResume: () => void;
}) {
  const Icon = ICON[kindOf(line)];
  const state = lineState(line, view, actions);
  const share =
    state.kind === "done"
      ? 100
      : state.kind === "running"
        ? (state.percent ?? 0)
        : 0;
  const running = lineRunning(line, actions);
  const left = toResume(line, view, actions);
  return (
    // The tile of « ce qu'il faut pour écouter », its size giving way to the progress,
    // which keeps its place at the bottom whatever the name's length.
    <div className="cl-onb__tile">
      {/* The progress goes round the icon: nothing moves as it grows. */}
      <span className="cl-ring" data-done={state.kind === "done" || undefined}>
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
          {state.kind === "done" ? (
            <Check size={16} strokeWidth={2.5} aria-hidden />
          ) : (
            <Icon size={18} strokeWidth={1.75} aria-hidden />
          )}
        </span>
      </span>
      <span className="cl-onb__name">{line.label}</span>
      <span className="cl-onb__what">{WHAT[kindOf(line)]}</span>
      <div className="cl-missing__foot">
        <div className="cl-missing__row">
          {running ? (
            <button type="button" className="cl-linkbtn cl-missing__act" onClick={onStop}>
              Arrêter
            </button>
          ) : state.kind !== "done" &&
            left.models.length + left.environments.length > 0 ? (
            <button
              type="button"
              className="cl-linkbtn cl-missing__act"
              onClick={onResume}
            >
              {state.kind === "waiting" ? "Télécharger" : "Reprendre"}
            </button>
          ) : (
            <span />
          )}
          <span className="cl-onb__pct">
            {state.kind === "done"
              ? "Prêt"
              : state.kind === "running"
                ? state.percent === null
                  ? "En cours"
                  : `${state.percent} %`
                : state.kind === "failed"
                  ? "Échoué"
                  : state.kind === "stopped"
                    ? "Arrêté"
                    : "En attente"}
          </span>
        </div>
        {state.kind === "failed" && (
          <span className="cl-onb__failed">{state.error}</span>
        )}
      </div>
    </div>
  );
}
