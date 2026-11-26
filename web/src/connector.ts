import type {
  ConnectorAccess,
  ConnectorSettings,
  ConnectorTool,
} from "./api.ts";
import { formatDate } from "./format.ts";

/** What an assistant did, said with the words of the interface (ADR 0065). */
export const TOOL_LABEL: Record<ConnectorTool, string> = {
  chercher: "Recherche",
  lister_seances: "Liste des séances",
  lire_seance: "Lecture de la séance",
  lire_resume: "Lecture d'un résumé",
  lire_transcript: "Lecture du transcript",
};

/** The session a read was about: its title now, or why there is none. */
export function accessSubject(entry: ConnectorAccess): string | null {
  if (entry.session_id === null) return null;
  if (entry.session_deleted) return "une séance supprimée depuis";
  return entry.session_title
    ? `« ${entry.session_title} »`
    : entry.session_recorded_at
      ? `« Séance du ${formatDate(entry.session_recorded_at).toLowerCase()} »`
      : "une séance sans titre";
}

/** How a space is read by the connector, in a few words. */
export function spaceReading(
  space: ConnectorSettings["spaces"][number],
): string {
  if (!space.connector_access) return "fermé";
  return space.connector_names
    ? "accessible, avec les noms"
    : "accessible, noms masqués";
}

/** What an open connector actually reaches: nothing while no space is open to it. */
export function connectorReach(
  settings: ConnectorSettings,
): "closed" | "no-space" | "reads" {
  if (!settings.open) return "closed";
  return settings.spaces.some((s) => s.connector_access) ? "reads" : "no-space";
}

/** Whether a read gave the names: null for one that gave no session. */
export function accessNames(entry: ConnectorAccess): string | null {
  if (entry.names_shared === null) return null;
  return entry.names_shared ? "avec les noms" : "noms masqués";
}

/** Why the program the assistants launch is not ready: the service's words, else a
 *  sentence that still says where to look. */
export function launcherProblem(settings: ConnectorSettings): string | null {
  if (settings.launcher_ready) return null;
  return (
    settings.launcher_problem ??
    "Coulisses n'a pas pu préparer le programme que lancent les assistants ; le détail est dans le journal technique (Réglages › Avancé)."
  );
}
