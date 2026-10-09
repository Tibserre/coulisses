import type { AudioSource, MixFacts } from "./api.ts";

/** The source ids the service gives the tracks recorded beside the reference. */
export const SYSTEM_SOURCE_ID = "system";

function trouble(source: AudioSource, what: string): string {
  if (!source.file_present) return ` (${what} introuvable)`;
  if (source.duration_s === null) return ` (${what} illisible)`;
  if (source.duration_s === 0) return ` (${what} vide)`;
  return "";
}

/** How the session's page says what was recorded beside the reference: the computer's
 *  sound (mixed in for the processing), a second microphone (kept, not processed yet).
 *  `text` follows the date and duration; `title` says more on hover. */
export function extraTracks(
  others: AudioSource[],
  mix: MixFacts | null = null,
): { text: string; title: string } | null {
  const system = others.find((s) => s.source_id === SYSTEM_SOURCE_ID);
  const mics = others.filter((s) => s.source_id !== SYSTEM_SOURCE_ID);
  if (!system && mics.length === 0) return null;
  const parts: string[] = [];
  const titles: string[] = [];
  if (system) {
    const problem = trouble(system, "piste");
    if (problem) {
      parts.push(`son de l'ordinateur${problem}`);
      titles.push("Sans cette piste, le micro seul est traité : les personnes à distance peuvent manquer.");
    } else if (mix?.system_silent) {
      parts.push("son de l'ordinateur resté muet");
      titles.push(
        "Rien n'est arrivé de l'ordinateur pendant tout l'enregistrement : macOS ne l'a sans doute pas donné. Autorisez-le dans Réglages Système, Confidentialité et sécurité, Enregistrement de l'écran et de l'audio du système. Le micro seul est traité.",
      );
    } else {
      parts.push("son de l'ordinateur");
      titles.push(
        "Le micro et le son de l'ordinateur ont été enregistrés ensemble ; ils sont réunis pour le traitement et l'écoute.",
      );
    }
  }
  if (mics.length > 0) {
    const name = (s: AudioSource) => s.device ?? s.original_name;
    parts.push(`${mics.length + 1} micros${mics.map((s) => trouble(s, `piste « ${name(s)} »`)).join("")}`);
    titles.push(
      `Gardé${mics.length > 1 ? "s" : ""} en plus : ${mics.map(name).join(", ")}. Seul le micro principal est traité pour l'instant.`,
    );
  }
  return { text: parts.map((p) => ` · ${p}`).join(""), title: titles.join(" ") };
}
