/** What the stop of a recording said about its other tracks (the computer's sound stayed
 *  silent, a second microphone's file unreadable…), carried to the session's page that
 *  opens right after. This tab only; the session's page also says it under its title. */
const KEY = "coulisses.arret.";

export function keepStopProblem(sessionId: string, problem: string): void {
  try {
    // Added to what is already kept: two problems of one session are both said.
    const kept = sessionStorage.getItem(KEY + sessionId);
    sessionStorage.setItem(KEY + sessionId, kept ? `${kept}\n${problem}` : problem);
  } catch {
    // Not carried: a stop problem is still said under the session's title; an annotation
    // lost on leaving the page is then lost unsaid (sessionStorage refused, rare).
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
