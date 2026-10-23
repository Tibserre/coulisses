/** Where the processing stands, as the two discs say it (ADR 0058, animation of the
 *  processing): « Le texte » (transcription, then alignment) and « Les voix »
 *  (diarisation), run at the same time by the engine; then « Qui a dit quoi »
 *  (attribution), which joins them. Each disc's share comes from what the engine publishes
 *  (progress.json): nothing is made up; a stage with no progress counts as not started. */
import type { StageView } from "./api.ts";

/** Within « Le texte »: the transcription is most of the work, the alignment the rest. A
 *  share of the disc, not a measured time. */
const TEXT_WEIGHTS: Record<string, number> = { transcribe: 3, align: 1 };

function share(stage: StageView | undefined): number {
  if (!stage) return 0;
  if (stage.state === "succeeded") return 1;
  const p = stage.progress;
  if (
    (stage.state === "running" || stage.state === "stalled") &&
    p &&
    p.total > 0
  )
    return Math.min(1, Math.max(0, p.done / p.total));
  return 0;
}

export interface Discs {
  /** 0 to 1. */
  text: number;
  voices: number;
  /** Both done, « Qui a dit quoi » under way. */
  joining: boolean;
  /** A stage gives no news for a while: it may have stopped. */
  stalled: boolean;
  /** About this many minutes left, from about ten per hour of audio (spec §7.4); null
   *  when the length of the audio is unknown. */
  minutesLeft: number | null;
}

export function processingDiscs(
  stages: StageView[],
  durationS: number | null,
): Discs {
  const by = new Map(stages.map((s) => [s.stage, s]));
  const parts = Object.entries(TEXT_WEIGHTS).filter(([name]) => by.has(name));
  const weight = parts.reduce((sum, [, w]) => sum + w, 0);
  const text = weight
    ? parts.reduce((sum, [name, w]) => sum + w * share(by.get(name)), 0) /
      weight
    : 0;
  const voices = share(by.get("diarize"));
  const hours = (durationS ?? 0) / 3600;
  // The two run side by side: what is left is what the slower one has left.
  const left = 1 - Math.min(text, voices);
  return {
    text,
    voices,
    joining: text >= 1 && voices >= 1,
    stalled: stages.some((s) => s.state === "stalled"),
    minutesLeft: hours > 0 ? Math.max(1, Math.round(hours * 10 * left)) : null,
  };
}
