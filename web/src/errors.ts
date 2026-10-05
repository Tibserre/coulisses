/** Plain French for the errors a stage can end with. The engine's own message (English,
 *  technical) stays available in developer mode: an error is always shown (P8). */

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
  for (const [pattern, text] of KNOWN) if (pattern.test(raw)) return text;
  return "Le calcul a échoué. Le détail technique est visible en mode développeur.";
}
