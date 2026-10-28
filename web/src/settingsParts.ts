/** The tabs of the Settings (ADR 0051), sorted by what one comes to do. */
export type Part = "seances" | "redaction" | "transcription" | "avance";
export const PARTS: [Part, string][] = [
  ["seances", "Séances"],
  ["redaction", "Rédaction"],
  ["transcription", "Transcription"],
  ["avance", "Avancé"],
];
/** Tabs of earlier versions, still in links and in older messages. */
const FORMER: Record<string, Part> = {
  general: "seances",
  historique: "seances",
  modeles: "transcription",
  mac: "transcription",
  donnees: "avance",
};

/** The tab asked in the address (« #/reglages?onglet=avance »), else the first. */
export function partOf(asked: string | null): Part {
  if (asked && Object.hasOwn(FORMER, asked)) return FORMER[asked];
  return PARTS.some(([key]) => key === asked) ? (asked as Part) : "seances";
}

/** A folder said by its own name (« Comptes rendus »), never its path (ADR 0051). */
export function folderName(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/** Which code runs (ADR 0064), when it is not the published version itself:
 *  `v0.34.0-36-gcac1f05` between two versions, null on `v` + the version. */
export function buildShown(version: string, build: string): string | null {
  return build === `v${version}` ? null : build;
}
