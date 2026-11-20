import { useEffect, useState } from "react";
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
  linesRunning,
  linesToResume,
  onboardingDownload,
  progressLines,
  sizeWords,
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
  // What it follows stays the same while it downloads: a piece done keeps its tile.
  const [followed, setFollowed] = useState<Piece[] | null>(null);
  const [followedChoices, setFollowedChoices] = useState<LanguageChoice[] | null>(null);
  useEffect(() => {
    if (started && !followed) {
      setFollowed(pieces);
      setFollowedChoices(choices);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fixed once started
  }, [started]);
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
      {/* Once started, the progress shows right here: no click to see it. */}
      {started ? (
        <div className="cl-missing__inline">
          <MissingPanel
            view={view}
            pieces={followed ?? pieces}
            chosen={followedChoices ?? choices}
            startedAlready
            onStarted={onStarted}
            untitled
          />
        </div>
      ) : (
        <Button
          label="Voir ce qui manque"
          variant="primary"
          isDisabled={waitingLanguages}
          onClick={() => setOpen(true)}
        />
      )}
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
  actions,
}: {
  view: ModelsView;
  pieces: Piece[];
  chosen: LanguageChoice[];
  startedAlready: boolean;
  onStarted: () => void;
  onClose: () => void;
  /** The downloads as they go (read twice a second by the caller); else the view's. */
  actions?: ModelAction[];
}) {
  return (
    <Dialog
      isOpen
      onOpenChange={(isOpen) => !isOpen && onClose()}
      width={560}
      maxHeight="90dvh"
      aria-label="Ce qui manque"
    >
      <div className="cl-onb cl-onb--steps">
        <MissingPanel
          view={view}
          pieces={pieces}
          chosen={chosen}
          startedAlready={startedAlready}
          onStarted={onStarted}
          onClose={onClose}
          actions={actions}
        />
      </div>
    </Dialog>
  );
}

/** What lacks, then its progress, as tiles (ADR 0079): in the « Ce qui manque » window, or
 *  right in a page (`onClose` absent), where the progress shows without a click. */
export function MissingPanel({
  view,
  pieces,
  chosen,
  startedAlready,
  onStarted,
  onClose,
  actions = view.actions,
  untitled = false,
}: {
  view: ModelsView;
  pieces: Piece[];
  chosen: LanguageChoice[];
  startedAlready: boolean;
  onStarted: () => void;
  onClose?: () => void;
  actions?: ModelAction[];
  /** The page says it already, above. */
  untitled?: boolean;
}) {
  const inline = !onClose;
  const [plan, setPlan] = useState<{
    pieces: Piece[];
    chosen: LanguageChoice[];
  } | null>(startedAlready ? { pieces, chosen } : null);
  useEffect(() => {
    if (startedAlready) setPlan((current) => current ?? { pieces, chosen });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- what it follows, fixed once
  }, [startedAlready]);
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
  const title = plan ? "Téléchargement en cours" : "Ce qui manque";
  const download = (
    <Button
      label={`Télécharger · ${total.more ? "plus de " : total.approximate ? "environ " : ""}${gigabytes(total.bytes)}`}
      variant="primary"
      isLoading={working}
      isDisabled={!total.download.length && !total.install.length}
      onClick={() => void start()}
    />
  );
  const control = (
    <DownloadsControl
      lines={lines}
      view={view}
      actions={actions}
      onDone={async () => {
        await reread();
        onStarted();
      }}
      onError={setError}
    />
  );

  return (
    <>
      {untitled ? null : inline ? (
        <p className="cl-missing__status">{title}</p>
      ) : (
        <h2 className="cl-onb__title">{title}</h2>
      )}
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
                  {sizeWords(
                    sizeOf(line),
                    gigabytes,
                    shown.pieces.find((p) => p.kind === line.key)?.approximate,
                  )}
                </span>
              </div>
            );
          return (
            <ProgressTile
              key={line.key}
              line={line}
              view={view}
              actions={actions}
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
            {inline
              ? "Les séances seront traitées une fois tout là."
              : "La séance partira d'elle-même ensuite."}
          </p>
          <div className="cl-onb__right">
            {control}
            {onClose && (
              <Button label="Fermer" variant="primary" onClick={onClose} />
            )}
          </div>
        </div>
      ) : (
        <div className="cl-onb__actions cl-onb__actions--end">
          <div className="cl-onb__right">
            {onClose && (
              <Button label="Plus tard" variant="ghost" onClick={onClose} />
            )}
            {download}
          </div>
        </div>
      )}
    </>
  );
}

/** One piece's progress, as a tile (ADR 0079): the same in the onboarding and in « Ce qui
 *  manque ». Its state only: every piece is needed, so they stop and resume together, by
 *  the window's own buttons (`DownloadsControl`). */
export function ProgressTile({
  line,
  view,
  actions,
}: {
  line: ProgressLine;
  view: ModelsView;
  actions: ModelAction[];
}) {
  const Icon = ICON[kindOf(line)];
  const state = lineState(line, view, actions);
  const share =
    state.kind === "done"
      ? 100
      : state.kind === "running"
        ? (state.percent ?? 0)
        : 0;
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
      {/* Where the size was before it started: large, at the bottom, the same place. */}
      <span className="cl-onb__size" data-progress>
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
      {state.kind === "failed" && (
        <span className="cl-onb__failed">{state.error}</span>
      )}
    </div>
  );
}

/** The window's one control over the downloads (ADR 0079): « Tout arrêter » while any
 *  runs, « Reprendre » for what stopped or failed; nothing per piece. */
export function DownloadsControl({
  lines,
  view,
  actions,
  onDone,
  onError,
}: {
  lines: ProgressLine[];
  view: ModelsView;
  actions: ModelAction[];
  /** Read the models again: what stopped or started shows. */
  onDone: () => Promise<void> | void;
  onError: (message: string) => void;
}) {
  const [working, setWorking] = useState(false);
  const running = linesRunning(lines, actions);
  const left = linesToResume(lines, view, actions);
  const act = async (what: () => Promise<unknown>) => {
    setWorking(true);
    onError("");
    try {
      await what();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setWorking(false);
      await onDone();
    }
  };
  const resume = () =>
    void act(async () => {
      for (const key of left.models) await api.downloadModel(key);
      for (const name of left.environments) await api.installEnvironment(name);
    });
  const lagging = left.models.length + left.environments.length > 0;
  if (running.length)
    return (
      <>
        {/* A start partly refused: what waits can start beside what runs (P8). */}
        {lagging && (
          <Button
            label="Reprendre le reste"
            variant="ghost"
            isDisabled={working}
            onClick={resume}
          />
        )}
        <Button
          label="Tout arrêter"
          variant="ghost"
          isLoading={working}
          onClick={() =>
            void act(async () => {
              for (const a of running) await api.cancelModelAction(a.kind, a.name);
            })
          }
        />
      </>
    );
  if (lagging)
    return (
      <Button
        label="Reprendre"
        variant="ghost"
        isLoading={working}
        onClick={resume}
      />
    );
  return null;
}
