import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Dialog } from "@astryxdesign/core/Dialog";
import { Check } from "lucide-react";
import { api, type ModelAction, type ModelsView } from "../api.ts";
import { requestSystemAudio, useSystemAudio } from "../appBridge.ts";
import { gigabytes } from "../models.ts";
import {
  basePieces,
  languageChoices,
  onboardingDownload,
  progressLines,
  sizeWords,
  toResume,
  type LanguageChoice,
  type Piece,
  type ProgressLine,
} from "../onboarding.ts";
import {
  downloadEverything,
  lastModelsView,
  onStepsChanged,
  stepsChanged,
} from "../steps.ts";
import { useLanguages } from "./Languages.tsx";
import { ICON, LABELS, WHAT } from "./pieceWords.ts";
import { ProgressTile } from "./Missing.tsx";

const WELCOME = "Qui a dit ça, déjà ? Tout est là, mot pour mot.";
const WELCOME_WORDS = WELCOME.split(" ");
/** When the first word lights, and the gap between two words, in seconds. */
const WORD_START = 0.3;
const WORD_STEP = 0.27;
/** The welcome's drawn sound: bar heights, in px. */
const WAVE = [
  8, 14, 20, 12, 24, 18, 10, 22, 28, 16, 12, 20, 26, 14, 8, 18, 24, 12, 20, 16,
  10, 22, 14, 8, 18, 26, 20, 12, 16, 10, 20, 24, 14, 8, 16, 12, 6,
];
/** The sound is read over the time the sentence takes to light. */
const WAVE_SWEEP = WELCOME_WORDS.length * WORD_STEP;
const WAVE_BARS = WAVE.map((h, i) => <b key={i} style={{ height: h }} />);

const capital = (text: string) =>
  `${text.charAt(0).toUpperCase()}${text.slice(1)}`;

/** The first launch, one idea per step (ADR 0079, spec §7.12): welcome, what will be
 *  downloaded, the languages, the one total and « Télécharger » (the user's explicit
 *  decision, P1), each piece's progress with the computer's sound, then the summaries,
 *  optional. « Plus tard » or closing: asked again at the next launch. */
export function Onboarding({
  isOpen,
  actions,
  onStop,
  onClose,
}: {
  isOpen: boolean;
  actions: ModelAction[];
  /** A download or an install stopped (it resumes next time). */
  onStop: (action: ModelAction) => Promise<void>;
  onClose: () => void;
}) {
  const [step, setStep] = useState(1);
  // Which way the steps went, for the way the new one comes in: none for the first.
  const [shownStep, setShownStep] = useState(step);
  const [direction, setDirection] = useState<"next" | "back" | undefined>();
  if (step !== shownStep) {
    setShownStep(step);
    setDirection(step > shownStep ? "next" : "back");
  }
  // The new step replaces the button that was pressed: the keyboard goes on from its main
  // button (the last one), so Entrée carries on.
  const stepRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!direction) return;
    const buttons = stepRef.current?.querySelectorAll<HTMLButtonElement>(
      ".cl-onb__actions button",
    );
    const main = buttons?.[buttons.length - 1] ?? stepRef.current;
    main?.focus({ preventScroll: true });
  }, [step, direction]);
  const [view, setView] = useState<ModelsView | null>(lastModelsView);
  const [error, setError] = useState<string | null>(null);
  const { languages } = useLanguages(setError);
  const [chosen, setChosen] = useState<string[]>([]);
  const [working, setWorking] = useState(false);
  /** What « Télécharger » started: followed in step 5 even once it is all there. */
  const [plan, setPlan] = useState<{
    pieces: Piece[];
    chosen: LanguageChoice[];
  } | null>(null);
  /** Writing already possible (Ollama with a model): no step about it. */
  const [writing, setWriting] = useState<boolean | null>(null);
  const sound = useSystemAudio();

  useEffect(() => onStepsChanged(setView), []);
  useEffect(() => {
    api.engineModels().then(stepsChanged, (e: Error) => setError(e.message));
    api.models().then(
      (m) => setWriting(m.reachable && m.models.length > 0),
      // Unknown: the step stays, it only explains.
      () => setWriting(false),
    );
  }, []);

  const pieces = useMemo(() => (view ? basePieces(view) : []), [view]);
  const choices = useMemo(
    () =>
      view && languages ? languageChoices(languages, view.catalog.models) : [],
    [view, languages],
  );
  const picked = choices.filter((c) => chosen.includes(c.language.language));
  const last = writing ? 5 : 6;

  const start = async () => {
    setWorking(true);
    setError(null);
    try {
      await downloadEverything(onboardingDownload(pieces, picked));
      setPlan({ pieces, chosen: picked });
      setStep(5);
    } catch (e) {
      setError((e as Error).message);
      // Part of it started: followed in step 5, the refusal said there too (P8).
      if ((lastModelsView()?.actions ?? []).some((a) => a.state === "running")) {
        setPlan({ pieces, chosen: picked });
        setStep(5);
      }
    } finally {
      setWorking(false);
    }
  };

  /** A line's own downloads: stopped (they resume where they were), or started again. */
  const act = async (what: () => Promise<unknown>) => {
    setError(null);
    try {
      await what();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      try {
        stepsChanged(await api.engineModels());
      } catch (e) {
        setError((e as Error).message);
      }
    }
  };
  const stop = (line: ProgressLine) =>
    act(async () => {
      for (const a of actions.filter(
        (a) =>
          a.state === "running" &&
          (a.kind === "model"
            ? line.models.includes(a.name)
            : line.environments.includes(a.name)),
      ))
        await onStop(a);
    });
  const resume = (line: ProgressLine) =>
    act(async () => {
      if (!view) return;
      const left = toResume(line, view, actions);
      for (const key of left.models) await api.downloadModel(key);
      for (const name of left.environments) await api.installEnvironment(name);
    });

  const dots = (
    <div className="cl-onb__dots" aria-label={`Étape ${step} sur ${last}`}>
      {Array.from({ length: last }, (_, i) => (
        <span key={i} className="cl-onb__dot" data-on={i < step || undefined} />
      ))}
    </div>
  );
  const said = error && (
    <p className="cl-onb__error" role="alert">
      {error}
    </p>
  );

  let body: React.ReactNode;
  if (step === 1)
    body = (
      <>
        <h2 className="cl-onb__title">Bienvenue dans Coulisses</h2>
        {/* What Coulisses does, shown as a line of a transcript: the sentence turns
            from gray to black word by word while its sound fills with colour at the
            same pace (ADR 0079). */}
        <div className="cl-welcome">
          <p className="cl-welcome__who" aria-hidden>
            Vous<span>0:00</span>
          </p>
          <p className="cl-welcome__line">
            <span className="cl-sr-only">{WELCOME}</span>
            {WELCOME_WORDS.map((word, i) => (
              <span
                key={i}
                aria-hidden
                style={{ animationDelay: `${(WORD_START + i * WORD_STEP).toFixed(2)}s` }}
              >
                {word}{" "}
              </span>
            ))}
          </p>
          {/* The sound is read from left to right: an orange copy over the gray one,
              uncovered at the pace the sentence lights. */}
          <div className="cl-welcome__wave" aria-hidden>
            <div className="cl-welcome__bars">{WAVE_BARS}</div>
            <div
              className="cl-welcome__bars cl-welcome__bars--read"
              style={{
                animationDuration: `${WAVE_SWEEP.toFixed(2)}s`,
                animationDelay: `${WORD_START}s`,
              }}
            >
              {WAVE_BARS}
            </div>
          </div>
        </div>
        <p className="cl-onb__text">
          Coulisses écoute vos séances et en tire le texte, qui parle, et un
          compte rendu. Tout reste sur ce Mac.
        </p>
        <div className="cl-onb__actions">
          <Button label="Plus tard" variant="ghost" onClick={onClose} />
          <Button
            label="Commencer"
            variant="primary"
            onClick={() => setStep(2)}
          />
        </div>
      </>
    );
  else if (step === 2)
    body = (
      <>
        <h2 className="cl-onb__title">Ce qu'il faut pour écouter</h2>
        <p className="cl-onb__text">
          Téléchargé une fois ; ensuite, tout reste sur ce Mac.
        </p>
        <div className="cl-onb__tiles">
          {pieces.map((p) => {
            const Icon = ICON[p.kind];
            return (
              <div key={p.kind} className="cl-onb__tile">
                <span className="cl-onb__icon">
                  <Icon size={20} strokeWidth={1.75} aria-hidden />
                </span>
                <span className="cl-onb__name">{LABELS[p.kind]}</span>
                <span className="cl-onb__what">{WHAT[p.kind]}</span>
                <span
                  className="cl-onb__size"
                  data-unknown={p.bytes === null || undefined}
                >
                  {sizeWords(p.bytes, gigabytes, p.approximate)}
                </span>
              </div>
            );
          })}
        </div>
        {said}
        <div className="cl-onb__actions">
          <Button label="Retour" variant="ghost" onClick={() => setStep(1)} />
          <Button
            label="Suivant"
            variant="primary"
            onClick={() => setStep(3)}
          />
        </div>
      </>
    );
  else if (step === 3) {
    const names = picked.map((c) => c.language.label.toLocaleLowerCase("fr"));
    const added = picked.reduce<number | null>(
      (sum, c) => (sum === null || c.bytes === null ? null : sum + c.bytes),
      0,
    );
    body = (
      <>
        <h2 className="cl-onb__title">Dans quelles langues ?</h2>
        <p className="cl-onb__text">
          Le français est inclus. Ajoutez celles dont vous avez besoin ;
          d'autres pourront venir plus tard.
        </p>
        <div className="cl-onb__langs">
          <button
            type="button"
            className="cl-onb__lang"
            aria-pressed="true"
            disabled
          >
            <span className="cl-onb__name">Français</span>
            <span className="cl-onb__what">Inclus</span>
            <span className="cl-onb__check">
              <Check size={12} strokeWidth={3} aria-hidden />
            </span>
          </button>
          {choices.map((c) => {
            const on = chosen.includes(c.language.language);
            return (
              <button
                key={c.language.language}
                type="button"
                className="cl-onb__lang"
                aria-pressed={on}
                onClick={() =>
                  setChosen((list) =>
                    on
                      ? list.filter((l) => l !== c.language.language)
                      : [...list, c.language.language],
                  )
                }
              >
                <span className="cl-onb__name">{c.language.label}</span>
                <span className="cl-onb__what">
                  {sizeWords(c.bytes, gigabytes)}
                </span>
                {on && (
                  <span className="cl-onb__check">
                    <Check size={12} strokeWidth={3} aria-hidden />
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <div className="cl-onb__added">
          <span className="cl-onb__text">
            {names.length === 0
              ? "Le français seulement"
              : `${names.length > 1 ? "Langues ajoutées" : "Langue ajoutée"} : ${names.join(", ")}`}
          </span>
          {names.length > 0 && (
            <b>{added === null ? "selon ce Mac" : `+ ${gigabytes(added)}`}</b>
          )}
        </div>
        {said}
        <div className="cl-onb__actions">
          <Button label="Retour" variant="ghost" onClick={() => setStep(2)} />
          <Button
            label="Suivant"
            variant="primary"
            onClick={() => setStep(4)}
          />
        </div>
      </>
    );
  } else if (step === 4) {
    const total = onboardingDownload(pieces, picked);
    const align = pieces.find((p) => p.kind === "align");
    const languageSizes = [
      ...(align ? [align.bytes] : []),
      ...picked.map((c) => c.bytes),
    ];
    const languageBytes = languageSizes.includes(null)
      ? null
      : languageSizes.reduce<number>((s, b) => s + (b ?? 0), 0);
    const languageNames = [
      ...(align ? ["français"] : []),
      ...picked.map((c) => c.language.label.toLocaleLowerCase("fr")),
    ];
    const segments = [
      ...pieces
        .filter((p) => p.kind === "transcribe")
        .map((p) => ({
          key: "transcribe",
          label: LABELS.transcribe,
          bytes: p.bytes,
          approximate: false,
        })),
      ...(languageNames.length
        ? [
            {
              key: "align",
              label: capital(languageNames.join(", ")),
              bytes: languageBytes,
              approximate: false,
            },
          ]
        : []),
      ...pieces
        .filter((p) => p.kind === "diarize" || p.kind === "tools")
        .map((p) => ({
          key: p.kind,
          label: LABELS[p.kind],
          bytes: p.bytes,
          approximate: p.approximate ?? false,
        })),
    ];
    const known = segments.reduce((s, g) => s + (g.bytes ?? 0), 0);
    body = (
      <>
        <h2 className="cl-onb__title">Prêt à télécharger</h2>
        <div className="cl-onb__total">
          <span className="cl-onb__big">{gigabytes(total.bytes)}</span>
          <span className="cl-onb__text">
            {total.more
              ? "au moins, une seule fois"
              : total.approximate
                ? "environ, une seule fois"
                : "une seule fois"}
          </span>
        </div>
        <div
          className="cl-onb__stack"
          role="img"
          aria-label="Ce que compte ce total"
        >
          {segments.map((g) => (
            <span
              key={g.key}
              data-part={g.key}
              style={{
                width: `${g.bytes === null || known === 0 ? 2 : Math.max(2, (g.bytes / known) * 100)}%`,
              }}
            />
          ))}
        </div>
        <ul className="cl-onb__legend">
          {segments.map((g) => (
            <li key={g.key}>
              <i data-part={g.key} />
              {g.label}
              <em>
                {sizeWords(g.bytes, gigabytes, g.approximate)}
              </em>
            </li>
          ))}
        </ul>
        <p className="cl-onb__text">
          Vous pourrez l'arrêter : il reprendra là où il s'est arrêté.
        </p>
        {said}
        <div className="cl-onb__actions">
          <Button label="Retour" variant="ghost" onClick={() => setStep(3)} />
          <div className="cl-onb__right">
            <Button label="Plus tard" variant="ghost" onClick={onClose} />
            <Button
              label="Télécharger"
              variant="primary"
              isLoading={working}
              isDisabled={
                !view || (!total.download.length && !total.install.length)
              }
              onClick={() => void start()}
            />
          </div>
        </div>
      </>
    );
  } else if (step === 5 && plan && view) {
    const lines = progressLines(plan.pieces, plan.chosen, LABELS);
    body = (
      <>
        <h2 className="cl-onb__title">Téléchargement en cours</h2>
        <div className="cl-onb__tiles">
          {lines.map((line) => (
            <ProgressTile
              key={line.key}
              line={line}
              view={view}
              actions={actions}
              onStop={() => void stop(line)}
              onResume={() => void resume(line)}
            />
          ))}
        </div>
        <p className="cl-onb__note">
          Vous pouvez fermer cette fenêtre et déjà enregistrer : la séance sera
          traitée une fois prêt.
        </p>
        {(sound === "unknown" || sound === "denied") && (
          <div className="cl-onb__extra">
            <h3 className="cl-onb__subtitle">En attendant</h3>
            <div className="cl-onb__row">
              <div className="cl-onb__rowwhat">
                <span>Le son de l'ordinateur</span>
                <span className="cl-onb__what">
                  Pour les visios : la voix des autres participants
                </span>
              </div>
              <Button label="Autoriser" onClick={() => requestSystemAudio()} />
            </div>
          </div>
        )}
        {said}
        <div className="cl-onb__actions cl-onb__actions--end">
          <Button
            label={step < last ? "Suivant" : "Fermer"}
            variant="primary"
            onClick={() => (step < last ? setStep(6) : onClose())}
          />
        </div>
      </>
    );
  } else if (step === 6)
    body = (
      <>
        <span className="cl-onb__tag">Facultatif</span>
        <h2 className="cl-onb__title">Et des résumés ?</h2>
        <div className="cl-onb__card" aria-hidden>
          <span className="cl-onb__cardtitle">Compte rendu d'une séance</span>
          <span className="cl-onb__line" style={{ width: "92%" }} />
          <span className="cl-onb__line" style={{ width: "78%" }} />
          <span className="cl-onb__line" style={{ width: "85%" }} />
          <span className="cl-onb__line" style={{ width: "40%" }} />
        </div>
        <div className="cl-onb__pair">
          <div data-with>
            <b>Avec Ollama</b>
            <span>
              Un compte rendu de chaque séance, rédigé sur ce Mac. Une app
              gratuite à installer.
            </span>
          </div>
          <div>
            <b>Sans</b>
            <span>
              Tout le reste marche : le texte, les voix, la recherche, l'export.
            </span>
          </div>
        </div>
        <div className="cl-onb__actions">
          <Button label="Retour" variant="ghost" onClick={() => setStep(5)} />
          <div className="cl-onb__right">
            <Button label="Pas maintenant" variant="ghost" onClick={onClose} />
            <Button
              label="Installer Ollama"
              variant="primary"
              onClick={() => {
                window.location.hash = "#/reglages?onglet=redaction";
                onClose();
              }}
            />
          </div>
        </div>
      </>
    );

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => !open && onClose()}
      width={560}
      maxHeight="90dvh"
      aria-label="Premier lancement de Coulisses"
    >
      <div className="cl-onb cl-onb--steps">
        {dots}
        {/* Each step comes in from the side it is on (ADR 0079): the window stays. */}
        <div
          key={step}
          ref={stepRef}
          className="cl-onb__step"
          data-direction={direction}
          tabIndex={-1}
        >
          {body}
        </div>
      </div>
    </Dialog>
  );
}
