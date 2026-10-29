import type { Language, ProcessingWait } from "./api.ts";
import { formatDate } from "./format.ts";
import { sessionHref } from "./library.ts";
import { gigabytes } from "./models.ts";

/** The default language, the only one the application names (ADR 0072, P6). */
export const FRENCH = "fr";

/** Its name inside a sentence: « anglais ». */
export function languageWord(label: string): string {
  return label.toLocaleLowerCase("fr");
}

/** Its name with its article: « l'anglais », « le français ». */
export function theLanguage(label: string): string {
  const word = languageWord(label);
  return /^[aeiouyàâéèêîôû]/.test(word) ? `l'${word}` : `le ${word}`;
}

/** The engine's name for a code; null for a language it no longer offers. */
export function labelOf(languages: Language[], code: string): string | null {
  return languages.find((l) => l.language === code)?.label ?? null;
}

/** « En anglais », said above a session's title; a language no longer offered says so. */
export function inLanguage(languages: Language[], code: string): string {
  const label = labelOf(languages, code);
  return label ? `En ${languageWord(label)}` : "Langue plus prise en charge";
}

/** A version's language (read in its provenance); null when it should say it and does not:
 *  « langue inconnue », never French (P7). */
export function versionLanguage(
  languages: Language[],
  code: string | null,
): string {
  if (code === null) return "langue inconnue";
  const label = labelOf(languages, code);
  return label ? languageWord(label) : "langue plus prise en charge";
}

export type LanguageState =
  | { kind: "installed" }
  | { kind: "downloading"; done: number; total: number }
  | { kind: "failed"; error: string }
  | { kind: "missing"; bytes: number };

/** Where a language stands on this Mac, from its models and their downloads. */
export function languageState(language: Language): LanguageState {
  if (language.installed) return { kind: "installed" };
  const running = language.downloads.filter((a) => a.state === "running");
  if (running.length) {
    const done = running.reduce((sum, a) => sum + a.done_bytes, 0);
    const known = running.reduce((sum, a) => sum + (a.total_bytes ?? 0), 0);
    // What is still to fetch counts too: one bar for the language, never one per model.
    return {
      kind: "downloading",
      done,
      total: Math.max(known, language.download_bytes),
    };
  }
  const failed = language.downloads.find((a) => a.state === "failed");
  if (failed)
    return {
      kind: "failed",
      error: failed.error ?? "Le téléchargement a échoué.",
    };
  return { kind: "missing", bytes: language.download_bytes };
}

/** The share downloaded, 0 to 100. */
export function downloadPercent(done: number, total: number): number {
  return total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
}

/** What a choice says beside its name: « installé », « à télécharger · 1,3 Go »… */
export function languageNote(language: Language): string {
  const state = languageState(language);
  switch (state.kind) {
    case "installed":
      return "installé";
    case "downloading":
      return `téléchargement : ${downloadPercent(state.done, state.total)} %`;
    case "failed":
      return "téléchargement échoué";
    case "missing":
      return `à télécharger · ${gigabytes(state.bytes)}`;
  }
}

/** Whether a session's language has something to say above its title: another language
 *  is on this Mac (or coming), or the session is not in French. All in French: nothing new. */
export function languageWorthShowing(
  languages: Language[],
  code: string,
): boolean {
  if (code !== FRENCH) return true;
  return languages.some(
    (l) =>
      l.language !== FRENCH &&
      (l.installed || languageState(l).kind === "downloading"),
  );
}

/** Why a language cannot be removed, one line per use; empty when nothing needs it. */
export function languageUses(
  language: Language,
): { key: string; name: string; why: string; href: string }[] {
  return [
    ...language.used_by.spaces.map((s) => ({
      key: `space-${s.id}`,
      name: s.archived ? `${s.name} (archivé)` : s.name,
      why: "Ses nouvelles séances sont dans cette langue",
      href: `#/espaces/${s.id}`,
    })),
    ...language.used_by.waiting_sessions.map((s) => ({
      key: `session-${s.id}`,
      name: s.title ?? `Séance du ${formatDate(s.recorded_at).toLowerCase()}`,
      why: "Son traitement attend, dans cette langue",
      href: sessionHref(s.id),
    })),
  ];
}

/** What a waiting processing says (ADR 0072): its title and its sentence. */
export function waitWords(
  wait: ProcessingWait,
  language: Language | undefined,
): {
  title: string;
  text: string;
  downloading: { done: number; total: number } | null;
} {
  if (wait.reason === "language_unsupported" || !wait.label)
    return {
      title: "La langue de cette séance n'est plus prise en charge",
      text: "Choisissez une autre langue au-dessus du titre : le traitement partira dans celle-ci.",
      downloading: null,
    };
  const word = languageWord(wait.label);
  const state = language ? languageState(language) : null;
  if (state?.kind === "downloading")
    return {
      title: `En attente du modèle ${word}`,
      text: "Le traitement part de lui-même dès que le téléchargement est fini. Les autres séances ne l'attendent pas.",
      downloading: { done: state.done, total: state.total },
    };
  return {
    title: `Le modèle ${word} n'est pas sur ce Mac`,
    text: `Le traitement attend ce modèle (${gigabytes(wait.download_bytes)}). Rien ne se télécharge sans vous ; les autres séances ne l'attendent pas.`,
    downloading: null,
  };
}
