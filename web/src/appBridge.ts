import { useEffect, useState } from "react";

/** What Coulisses.app, the published app in the Dock, gives the page (ADR 0040): its
 *  updates, run by Sparkle in the app itself, never by the service. Absent from the
 *  development app, from an app run from a repository and from a browser: the updates
 *  section then says so, and « Mettre à jour » never shows. */

export interface UpdatesState {
  /** Looks for a new version once a day (after the user's consent). */
  automatic: boolean;
  /** The last search, ISO 8601, or null if none yet. */
  lastCheck: string | null;
  /** A new version was found and waits for a click (ADR 0051): « Mettre à jour » in the
   *  sidebar. Set only once the page has announced that it shows it (`announceReminder`);
   *  otherwise Sparkle opens its own window, as before. It may stay true during a recording:
   *  the click is then refused by the app, said in French. */
  ready: boolean;
}

/** The event the app sends on the page when its updates' state changes. */
export const UPDATES_CHANGED = "coulisses:mises-a-jour";

interface AppMessages {
  postMessage(message: { action: string; value?: boolean }): void;
}

interface AppWindow {
  coulissesApp?: { updates?: Partial<UpdatesState> };
  webkit?: { messageHandlers?: { coulisses?: AppMessages } };
}

export interface Updates {
  state: UpdatesState;
  setAutomatic(on: boolean): void;
  checkNow(): void;
  /** Tells the app the page shows « Mettre à jour » (true), or no longer can (false). Once
   *  per mounting, never on each event: the app answers every message with the event. */
  announceReminder(on: boolean): void;
}

/** The app's updates, or null where there are none (see above). */
export function appUpdates(win: unknown = globalThis): Updates | null {
  const app = win as AppWindow;
  const given = app.coulissesApp?.updates;
  const messages = app.webkit?.messageHandlers?.coulisses;
  if (!given || !messages) return null;
  return {
    state: {
      automatic: given.automatic === true,
      lastCheck: typeof given.lastCheck === "string" ? given.lastCheck : null,
      ready: given.ready === true,
    },
    setAutomatic: (on) =>
      messages.postMessage({ action: "mises-a-jour-automatiques", value: on }),
    checkNow: () => messages.postMessage({ action: "rechercher-mises-a-jour" }),
    announceReminder: (on) =>
      messages.postMessage({ action: "rappel-mises-a-jour", value: on }),
  };
}

/** Whether a new version waits for a click, for a frame that stays mounted (ADR 0051): it
 *  announces the reminder once when mounted and withdraws it when unmounted, so a version
 *  found meanwhile is never shown nowhere; then it follows the app's event. */
export function useUpdateReady(): boolean {
  const [ready, setReady] = useState(() => appUpdates()?.state.ready ?? false);
  useEffect(() => {
    const read = () => setReady(appUpdates()?.state.ready ?? false);
    window.addEventListener(UPDATES_CHANGED, read);
    appUpdates()?.announceReminder(true);
    read();
    return () => {
      window.removeEventListener(UPDATES_CHANGED, read);
      appUpdates()?.announceReminder(false);
    };
  }, []);
  return ready;
}
