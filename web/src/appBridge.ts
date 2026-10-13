/** What Coulisses.app, the published app in the Dock, gives the page (ADR 0040): its
 *  updates, run by Sparkle in the app itself, never by the service. Absent from the
 *  development app, from an app run from a repository and from a browser: the updates
 *  section is then not shown. */

export interface UpdatesState {
  /** Looks for a new version once a day (after the user's consent). */
  automatic: boolean;
  /** The last search, ISO 8601, or null if none yet. */
  lastCheck: string | null;
}

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
    },
    setAutomatic: (on) =>
      messages.postMessage({ action: "mises-a-jour-automatiques", value: on }),
    checkNow: () => messages.postMessage({ action: "rechercher-mises-a-jour" }),
  };
}
