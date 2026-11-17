/** The words of the audio's keeping (spec §7.10), kept apart to be tested. */
import type { AudioStatus, DeletionLogEntry } from "./api.ts";

const DAY = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long" });
const DAY_YEAR = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric" });

/** « 14 octobre », with the year when it is not the current one. */
export function formatDay(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  const text = (when.getFullYear() === now.getFullYear() ? DAY : DAY_YEAR).format(when);
  return text.replace(/^1 /, "1er "); // « le 1er octobre »
}

/** What the session's header says of its audio; null when there is nothing to say (kept
 *  for a long while yet, or not processed). */
export function audioLine(audio: AudioStatus, now: Date = new Date()): string | null {
  switch (audio.state) {
    case "kept":
      return "audio gardé";
    case "removed":
      return audio.removed_at
        ? `audio supprimé le ${formatDay(audio.removed_at, now)}`
        : "audio supprimé";
    case "announced":
      // A day to come: said as to come, never as if it were done.
      return audio.purge_on ? `suppression de l'audio le ${formatDay(audio.purge_on, now)}` : null;
    default:
      return null;
  }
}

/** A message left for the library page by a page that just went away (a deleted
 *  session). Per tab, read once. */
const FLASH_KEY = "coulisses.message";

export function leaveMessage(message: string): void {
  try {
    window.sessionStorage.setItem(FLASH_KEY, message);
  } catch {
    // Storage blocked: the message is lost with the page; the journal keeps it.
  }
}

export function takeMessage(): string | null {
  try {
    const message = window.sessionStorage.getItem(FLASH_KEY);
    window.sessionStorage.removeItem(FLASH_KEY);
    return message;
  } catch {
    return null;
  }
}

export const LOG_KIND: Record<DeletionLogEntry["kind"], string> = {
  purge: "Audio purgé à échéance",
  audio_deletion: "Audio supprimé à la main",
  session_deletion: "Séance supprimée",
  conversion: "Pistes gardées en FLAC, sans perte",
  backup_pruning: "Anciennes copies de la base",
};

/** The value after `value` in `steps` (or before it): a value set elsewhere, between
 *  two steps, goes to the next one. */
export function nextStep(steps: readonly number[], value: number, up: boolean): number {
  const sorted = [...steps].sort((a, b) => a - b);
  const next = up
    ? sorted.find((s) => s > value)
    : [...sorted].reverse().find((s) => s < value);
  return next ?? value;
}

/** The keepings offered (spec §7.10): a week at least, three months at most. */
export const RETENTION_CHOICES = [7, 14, 30, 60, 90];

/** The choices shown: those offered, and the one kept if it was set to another value
 *  before, so that what is kept is always shown and never silently changed. */
export function retentionChoices(kept: number): number[] {
  return RETENTION_CHOICES.includes(kept)
    ? RETENTION_CHOICES
    : [...RETENTION_CHOICES, kept].sort((a, b) => a - b);
}

/** What is written when a keeping is chosen: the notice kept as it is, never above the
 *  keeping (the service refuses a notice longer than the keeping). */
export function retentionWrite(
  days: number,
  noticeDays: number,
): { retention_days: number; notice_days: number } {
  return { retention_days: days, notice_days: Math.min(noticeDays, days) };
}

/** Whole calendar days from today to that day, in local time: 0 today, 1 tomorrow. */
export function daysUntil(iso: string, now: Date = new Date()): number {
  const day = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((day(new Date(iso)) - day(now)) / 86_400_000);
}

/** « aujourd'hui », « demain », « dans 3 jours ». A day already past (a purge not run yet,
 *  the Mac asleep) reads as today: it is the next thing to happen. */
export function untilWords(days: number): string {
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "demain";
  return `dans ${days} jours`;
}

/** The reminders before a purge, said once: « Rappel 7 jours avant », « Rappel 7 jours,
 *  puis 3 jours avant ». */
export function remindersLine(days: number[]): string {
  const sorted = [...new Set(days)].filter((d) => d > 0).sort((a, b) => b - a);
  if (sorted.length === 0) return "Sans rappel";
  const said = sorted.map((d) => (d === 1 ? "1 jour" : `${d} jours`));
  return `Rappel ${said.slice(0, -1).map((s) => `${s}, puis `).join("")}${said.at(-1)} avant`;
}

/** Sessions whose audio went (purged or deleted by hand) while their text stayed, as far
 *  as the log read goes. A session deleted since, whole, is not counted: nothing of it is
 *  left. */
export function sessionsWithoutAudio(journal: DeletionLogEntry[]): number {
  const deleted = new Set(
    journal.filter((e) => e.kind === "session_deletion").map((e) => e.session_id),
  );
  return new Set(
    journal
      .filter(
        (e) =>
          (e.kind === "purge" || e.kind === "audio_deletion") &&
          e.session_id &&
          !deleted.has(e.session_id),
      )
      .map((e) => e.session_id),
  ).size;
}
