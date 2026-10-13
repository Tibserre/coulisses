/** Plain French for why a stage failed, from the engine's error code (engine ADR 0021,
 *  table in its README) and its details. The engine's own message (English, technical)
 *  stays available in developer mode: an error is always shown (P8). */
import type { StageView } from "./api.ts";

type StageError = Pick<StageView, "error" | "error_code" | "error_details">;

function text(details: Record<string, unknown> | null, key: string): string {
  const value = details?.[key];
  return value == null ? "?" : String(value);
}

/** What went wrong and what to do, for a stage that failed. */
export function describeStageError(stage: StageError): string | null {
  const d = stage.error_details;
  switch (stage.error_code) {
    case "model_missing":
      return `Un modèle nécessaire n'est pas installé (${text(d, "model")}). Téléchargez-le dans Réglages, onglet Transcription, puis reprenez.`;
    case "model_altered":
      return `Le modèle ${text(d, "model")} est abîmé : dans Réglages, onglet Transcription, supprimez-le puis retéléchargez-le, et reprenez.`;
    case "environment_missing":
      return `L'environnement de calcul ${text(d, "environment")} n'est pas installé. Installez-le dans Réglages, onglet Transcription, puis reprenez.`;
    case "audio_unreadable":
      return "L'enregistrement n'a pas pu être lu : fichier absent, abîmé, ou sans son.";
    case "too_few_speakers":
      return `${text(d, "found")} voix trouvées pour ${text(d, "expected")} présents indiqués. Les voix ne sont jamais fusionnées pour atteindre le compte : reprenez avec moins de présents.`;
    case "out_of_memory":
      return d?.signal
        ? "Le système a arrêté le calcul, sans doute faute de mémoire. Fermez d'autres applications, puis reprenez."
        : "Le calcul a manqué de mémoire. Fermez d'autres applications, puis reprenez.";
    case "interrupted":
      return "Interrompue : Coulisses a été arrêté pendant le calcul. Reprenez le traitement.";
    case "cancelled":
      return "Annulée.";
    case "scratch_not_cleared":
      return `Un dossier temporaire n'a pas pu être vidé et peut contenir de l'audio : supprimez-le (${text(d, "path")}).`;
    case "engine_failed":
      return "Le calcul a échoué. Le détail technique est visible en mode développeur.";
    default:
      return friendlyError(stage.error);
  }
}

/** Errors without a code: the application's own, and runs closed before engine v1.3.0. */
const KNOWN: Array<[RegExp, string]> = [
  [/^Interrupted\b/, "Interrompue : Coulisses a été arrêté pendant le calcul. Reprenez le traitement."],
  [/^Cancelled\b/, "Annulée."],
  [/^ChildCrash\b/, "Le calcul s'est arrêté brutalement, peut-être faute de mémoire."],
  [/^ApplicationStoppingError\b/, "Pas lancée : Coulisses s'arrêtait."],
  [/refuse de la clore/, "Un calcul précédent semble encore tourner ; relancez Coulisses plus tard."],
  [/Interrompue avant d'avoir démarré/, "Interrompue avant d'avoir démarré."],
];

export function friendlyError(raw: string | null): string | null {
  if (raw == null) return null;
  for (const [pattern, message] of KNOWN) if (pattern.test(raw)) return message;
  return "Le calcul a échoué. Le détail technique est visible en mode développeur.";
}
