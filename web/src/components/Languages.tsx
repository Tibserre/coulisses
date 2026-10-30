import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactElement,
} from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Popover } from "@astryxdesign/core/Popover";
import { Text } from "@astryxdesign/core/Text";
import { Check, ChevronDown } from "lucide-react";
import { api, type Language, type ProcessingWait, type Session } from "../api.ts";
import { gigabytes } from "../models.ts";
import {
  downloadPercent,
  FRENCH,
  inLanguage,
  labelOf,
  languageNote,
  languageState,
  languageWord,
  languageWorthShowing,
  theLanguage,
  waitWords,
} from "../languages.ts";

/** The languages of the chain (GET /api/langues), read again every second while one of
 *  them downloads. */
export function useLanguages(onError?: (message: string) => void) {
  const [languages, setLanguages] = useState<Language[] | null>(null);
  // The latest handler, without reading the languages again each time it changes.
  const report = useRef(onError);
  report.current = onError;
  const reload = useCallback(
    () =>
      api
        .languages()
        .then(setLanguages, (e: Error) => report.current?.(e.message)),
    [],
  );
  useEffect(() => {
    void reload();
  }, [reload]);
  const downloading =
    languages?.some((l) => languageState(l).kind === "downloading") ?? false;
  useEffect(() => {
    if (!downloading) return;
    const timer = window.setInterval(() => void reload(), 1000);
    return () => window.clearInterval(timer);
  }, [downloading, reload]);
  return { languages, reload };
}

/** The list of the languages, floating under what opens it (ADR 0072): each with where it
 *  stands on this Mac (« installé », « à télécharger · 1,3 Go »). */
export function LanguagePick({
  languages,
  value,
  title,
  intro,
  onPick,
  children,
}: {
  languages: Language[];
  value: string;
  /** What is chosen, said to assistive technologies (« Langue de la séance »). */
  title: string;
  /** A sentence above the list: what a choice does. */
  intro?: string;
  onPick: (language: Language) => void;
  /** What opens it: a button. */
  children: ReactElement;
}) {
  const [isOpen, setOpen] = useState(false);
  return (
    <Popover
      isOpen={isOpen}
      onOpenChange={setOpen}
      label={title}
      placement="below"
      alignment="start"
      width={320}
      padding={1}
      content={
        <div className="cl-languagepick">
          {intro && (
            <Text as="p" type="supporting">
              {intro}
            </Text>
          )}
          <ul className="cl-spacepick" aria-label={title}>
            {languages.map((l) => (
              <li key={l.language}>
                <button
                  type="button"
                  className="cl-spacepick__item"
                  aria-current={l.language === value || undefined}
                  onClick={() => {
                    setOpen(false);
                    if (l.language !== value) onPick(l);
                  }}
                >
                  <span className="cl-modelpick__option">
                    <span>{l.label}</span>
                    <span className="cl-modelpick__about">
                      {languageNote(l)}
                    </span>
                  </span>
                  {l.language === value && (
                    <Check size={16} strokeWidth={1.75} aria-hidden />
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      }
    >
      {children}
    </Popover>
  );
}

/** Downloads a language's missing models, each by the route that exists (ADR 0036), with
 *  its progress, its stop and its resumption. Always asked first (P1, spec §7.12). */
export function LanguageDownloadDialog({
  language,
  after,
  onClose,
  onStarted,
}: {
  /** The language to download; null: closed. */
  language: Language | null;
  /** What happens meanwhile, in a sentence (« La séance l'attend »). */
  after?: string;
  onClose: () => void;
  /** Read the languages again: what started is shown with its progress. */
  onStarted: () => void;
}) {
  const [working, setWorking] = useState(false);
  // Refused: said in the window itself, which stays open (P8), wherever it was opened from.
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setError(null), [language]);
  const the = language ? theLanguage(language.label) : "";
  const size = language ? gigabytes(language.download_bytes) : "";
  const start = async () => {
    if (!language) return;
    setWorking(true);
    let started = 0;
    try {
      for (const key of language.missing_models) {
        await api.downloadModel(key);
        started += 1;
      }
      onClose();
    } catch (e) {
      const said = (e as Error).message;
      setError(started ? `${started} sur ${language.missing_models.length} ont démarré ; le suivant a été refusé : ${said}` : said);
    } finally {
      setWorking(false);
      onStarted();
    }
  };
  return (
    <AlertDialog
      isOpen={language !== null}
      onOpenChange={(open) => !open && onClose()}
      title={`${the.charAt(0).toUpperCase()}${the.slice(1)} n'est pas encore sur ce Mac`}
      description={
        language
          ? `Pour transcrire en ${languageWord(language.label)}, Coulisses a besoin d'un modèle de ${size}, téléchargé une fois depuis internet ; ensuite, tout reste sur ce Mac. Vous pouvez l'arrêter : il reprendra là où il s'est arrêté.${after ? ` ${after}` : ""}${error ? ` Le téléchargement n'a pas démarré en entier : ${error}` : ""}`
          : ""
      }
      actionLabel={`Télécharger (${size})`}
      actionVariant="primary"
      cancelLabel="Plus tard"
      isActionLoading={working}
      onAction={() => void start()}
    />
  );
}

/** A session's language, above its title (ADR 0072), only when it has something to say.
 *  Before its text is made, a choice changes it at once; after, it asks to redo the text
 *  in that language: never a silent change. */
export function SessionLanguage({
  session,
  languages,
  onChanged,
  onRedo,
  onDownload,
  onError,
}: {
  session: Session;
  languages: Language[];
  onChanged: (session: Session) => void;
  /** Its text is made: « Refaire le texte » in that language. */
  onRedo: (language: string) => void;
  /** Chosen though not on this Mac: its download offered. */
  onDownload: (language: Language) => void;
  onError: (message: string) => void;
}) {
  if (!languageWorthShowing(languages, session.language)) return null;
  const label = labelOf(languages, session.language);
  return (
    <LanguagePick
      languages={languages}
      value={session.language}
      title="Langue de la séance"
      intro={
        session.language_editable
          ? "Le traitement se fera dans cette langue."
          : `Le texte de cette séance est ${label ? `en ${languageWord(label)}` : "dans une langue plus prise en charge"}. Choisir une autre langue refait le texte ; les voix et leurs noms sont gardés.`
      }
      onPick={(l) => {
        if (!session.language_editable) {
          onRedo(l.language);
          return;
        }
        api.setSessionLanguage(session.id, l.language).then(
          (next) => {
            onChanged(next);
            if (!l.installed) onDownload(l);
          },
          (e: Error) => onError(e.message),
        );
      }}
    >
      <button type="button" className="cl-crumbbtn">
        {inLanguage(languages, session.language)}
        <ChevronDown size={13} strokeWidth={1.75} aria-hidden />
      </button>
    </LanguagePick>
  );
}

/** A processing waiting for its language (ADR 0072): what it waits for, the download and
 *  its progress, or another language. Nothing is fetched alone (P1). */
export function LanguageWait({
  session,
  wait,
  languages,
  onChanged,
  onDownload,
  onStopped,
}: {
  session: Session;
  wait: ProcessingWait;
  /** Null while read (or unreadable, said elsewhere): what it waits for is said anyway. */
  languages: Language[] | null;
  onChanged: (session: Session) => void;
  onDownload: (language: Language) => void;
  /** Its download stopped: the languages are read again. */
  onStopped: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const language = languages?.find((l) => l.language === wait.language);
  const words = waitWords(wait, language);
  const act = async (what: () => Promise<void>) => {
    setError(null);
    try {
      await what();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <section className="cl-ask">
      <Heading level={3}>{words.title}</Heading>
      <Text color="secondary">{words.text}</Text>
      {words.downloading && (
        <div className="cl-models__progress">
          <ProgressBar
            label={`Téléchargement du modèle ${languageWord(wait.label ?? "")}`}
            value={downloadPercent(words.downloading.done, words.downloading.total)}
            hasValueLabel
          />
          <Text type="supporting">
            {gigabytes(words.downloading.done)} sur {gigabytes(words.downloading.total)}
          </Text>
        </div>
      )}
      <div className="cl-ask__actions">
        {wait.reason === "model_missing" && !words.downloading && language && (
          <Button
            variant="primary"
            label={`Télécharger (${gigabytes(wait.download_bytes)})`}
            onClick={() => onDownload(language)}
          />
        )}
        {wait.language !== FRENCH && (
          <Button
            label="Traiter en français"
            clickAction={() =>
              act(async () => onChanged(await api.setSessionLanguage(session.id, FRENCH)))
            }
          />
        )}
        {words.downloading && language && (
          <Button
            variant="ghost"
            label="Arrêter le téléchargement"
            clickAction={() =>
              act(async () => {
                for (const a of language.downloads.filter((d) => d.state === "running"))
                  await api.cancelModelAction("model", a.name);
                onStopped();
              })
            }
          />
        )}
      </div>
      {error && (
        <Text as="p" color="primary" type="supporting">
          {error}
        </Text>
      )}
    </section>
  );
}
