/**
 * Drafts kept in this browser while they are not saved: an action being written, the note
 * after a session. A per-viewer safety net only (P8: a draft is never lost to a click
 * elsewhere or a closed window); what counts is saved by the service.
 */
const PREFIX = "coulisses:brouillon:";

export function readDraft<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw == null ? null : (JSON.parse(raw) as T);
  } catch {
    return null; // storage refused (private window…): no draft to offer back
  }
}

export function writeDraft(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage refused: the draft stays on screen, the save on leaving still runs.
  }
}

export function clearDraft(key: string): void {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    // Nothing kept: nothing to clear.
  }
}
