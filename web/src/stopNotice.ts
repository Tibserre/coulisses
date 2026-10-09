/** What the stop of a recording said about its other tracks (the computer's sound stayed
 *  silent, a second microphone's file unreadable…), carried to the session's page that
 *  opens right after. This tab only; the session's page also says it under its title. */
const KEY = "coulisses.arret.";

export function keepStopProblem(sessionId: string, problem: string): void {
  try {
    sessionStorage.setItem(KEY + sessionId, problem);
  } catch {
    // Not carried: the session's page still says it under its title.
  }
}

export function takeStopProblem(sessionId: string): string | null {
  try {
    const problem = sessionStorage.getItem(KEY + sessionId);
    sessionStorage.removeItem(KEY + sessionId);
    return problem;
  } catch {
    return null;
  }
}
