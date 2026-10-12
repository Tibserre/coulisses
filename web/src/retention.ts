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
};

/** The value after `value` in `steps` (or before it), within `min` and `max`: a value
 *  set elsewhere, between two steps, goes to the next one. */
export function nextStep(
  steps: readonly number[],
  value: number,
  up: boolean,
  min: number,
  max: number,
): number {
  const sorted = [...steps].sort((a, b) => a - b);
  const next = up
    ? sorted.find((s) => s > value)
    : [...sorted].reverse().find((s) => s < value);
  if (next === undefined) return value;
  return Math.min(max, Math.max(min, next));
}
