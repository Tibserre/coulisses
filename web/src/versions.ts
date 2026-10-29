/** The words of the processing versions (spec §7.4, §7.6), kept apart to be tested. */
import type { Rerun, RerunFacts, Version } from "./api.ts";
import { plural } from "./format.ts";

/** What made a version, in a few words. */
export function versionOrigin(
  v: Pick<Version, "origin" | "min_voices">,
): string {
  if (v.origin === "all") return "tout refait";
  if (v.origin === "transcribe") return "transcription refaite";
  if (v.origin === "diarize")
    return v.min_voices ? `voix séparées à nouveau (au moins ${v.min_voices})` : "voix séparées à nouveau";
  return "premier traitement";
}

/** How a version's corrections were carried over from the one it replaced. */
export function carriedText(
  v: Pick<Version, "carried" | "not_carried">,
): string | null {
  if (v.carried == null) return null;
  const done = plural(
    v.carried,
    "correction reportée",
    "corrections reportées",
  );
  return v.not_carried
    ? `${done}, ${v.not_carried} à reprendre`
    : done;
}

/** About how long a rerun will compute: the time measured last time when there is one,
 *  otherwise about 10 minutes per hour of audio. */
export function rerunMinutes(
  facts: Pick<RerunFacts, "transcribe_s" | "diarize_s">,
  stage: Rerun,
  audioSeconds: number | null,
): { minutes: number; measured: boolean } | null {
  // All of it: the text and the voices are made side by side, the longer one sets the time.
  const measured =
    stage === "all"
      ? facts.transcribe_s != null && facts.diarize_s != null
        ? Math.max(facts.transcribe_s, facts.diarize_s)
        : null
      : stage === "transcribe"
        ? facts.transcribe_s
        : facts.diarize_s;
  if (measured != null)
    return { minutes: Math.max(1, Math.round(measured / 60)), measured: true };
  if (audioSeconds == null) return null;
  return {
    minutes: Math.max(1, Math.round((audioSeconds / 3600) * 10)),
    measured: false,
  };
}

/** The words saying what a transcription rerun will bring. */
export function transcribeGain(
  facts: Pick<RerunFacts, "glossary_added" | "engine_updated">,
): string {
  const parts: string[] = [];
  const added = facts.glossary_added;
  if (added.length) {
    const shown = added.slice(0, 4).join(", ");
    const more = added.length > 4 ? `, et ${added.length - 4} de plus` : "";
    parts.push(
      `${plural(added.length, "terme ajouté", "termes ajoutés")} au glossaire depuis la dernière fois (${shown}${more})`,
    );
  }
  if (facts.engine_updated)
    parts.push("le moteur de transcription a été mis à jour depuis");
  if (!parts.length)
    return "Rien n'a changé depuis la dernière transcription : le résultat sera probablement très proche.";
  const text = parts.join(" ; ");
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

export const RERUN_NAME: Record<Rerun, string> = {
  transcribe: "la transcription",
  diarize: "la séparation des voix",
  all: "tout le traitement",
};

/** While it runs, in a few words (above the transcript). */
export const RERUN_DOING: Record<Rerun, string> = {
  transcribe: "Le texte est refait",
  diarize: "Les voix sont refaites",
  all: "Le texte et les voix sont refaits",
};

/** Said under the people present when the processing did not take them (spec §7.1): the
 *  voices are separated from its start, so those checked later serve a rerun of the voices,
 *  offered once it is done and while the audio is there (§7.4). Nothing when they were taken. */
export function attendeesNotTaken(session: {
  attendees_taken: boolean | null;
  min_voices: number | null;
  job_state: string | null;
  audio: { state: string };
}): { text: string; rerun: boolean } | null {
  if (session.attendees_taken !== false) return null;
  const running = session.job_state === "queued" || session.job_state === "running";
  const searched =
    session.min_voices === null
      ? running
        ? "Le traitement cherche seul le nombre de voix"
        : "Le traitement a cherché seul le nombre de voix"
      : `${running ? "Le traitement cherche" : "Le traitement a cherché"} au moins ${session.min_voices} voix`;
  const rerun = session.job_state === "done" && session.audio.state !== "removed";
  if (session.audio.state === "removed")
    return { text: `${searched}. L'audio est supprimé : les voix ne se refont plus.`, rerun: false };
  return {
    text: `${searched} : ces présents serviront si vous refaites les voix${running ? ", une fois le traitement fini" : ""}.`,
    rerun,
  };
}
