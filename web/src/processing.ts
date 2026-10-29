/** Where the processing stands, as the two discs say it (ADR 0058, animation of the
 *  processing): « Le texte » (transcription, then alignment) and « Les voix »
 *  (diarisation), run at the same time by the engine; then « Qui a dit quoi »
 *  (attribution), which joins them. Each disc's share comes from what the engine publishes
 *  (progress.json): nothing is made up; a stage with no progress counts as not started. */
import type { StageView } from "./api.ts";

/** Within « Le texte »: the transcription is most of the work, the alignment the rest. A
 *  share of the disc, not a measured time. */
const TEXT_WEIGHTS: Record<string, number> = { transcribe: 3, align: 1 };

/** A stage under way stops short of full: only its end fills the disc. The engine counts
 *  each phase of a stage from zero (the diarisation has three, four with its pyannote
 *  net); since v1.13.0 it says which one out of how many, each an equal part (no phase
 *  is measured longer than another). Before, a phase done is not the stage done. */
const RUNNING_MAX = 0.9;

function share(stage: StageView | undefined): number {
  if (!stage) return 0;
  // To be redone and not started yet: the service shows the version's run, done but
  // stale; it is still all to do.
  if (stage.stale) return 0;
  if (stage.state === "succeeded") return 1;
  const p = stage.progress;
  if (
    (stage.state === "running" || stage.state === "stalled") &&
    p &&
    p.total > 0
  ) {
    const inPhase = Math.min(1, Math.max(0, p.done / p.total));
    const steps = Math.max(1, p.steps ?? 1);
    const step = Math.min(steps, Math.max(1, p.step ?? 1));
    return Math.min(RUNNING_MAX, (step - 1 + inPhase) / steps);
  }
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

/** `before`: the shares shown until now, for this session. A disc never goes back: when
 *  the engine starts a new phase from zero, it waits where it was. */
export function processingDiscs(
  stages: StageView[],
  durationS: number | null,
  before: Pick<Discs, "text" | "voices"> | null = null,
): Discs {
  const by = new Map(stages.map((s) => [s.stage, s]));
  const parts = Object.entries(TEXT_WEIGHTS).filter(([name]) => by.has(name));
  const weight = parts.reduce((sum, [, w]) => sum + w, 0);
  const text = Math.max(
    before?.text ?? 0,
    weight
      ? parts.reduce((sum, [name, w]) => sum + w * share(by.get(name)), 0) /
          weight
      : 0,
  );
  const voices = Math.max(before?.voices ?? 0, share(by.get("diarize")));
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

/** Whole seconds until a time the service measured (ISO), never below zero. */
export function secondsLeft(at: string, now: number): number {
  const target = Date.parse(at);
  return Number.isFinite(target) ? Math.max(0, Math.ceil((target - now) / 1000)) : 0;
}

/** What is left of the wait for the people present (ADR 0069), said plainly, with whom it
 *  will start by itself (those checked are saved at once). */
export function waitLeft(seconds: number, present: number): string {
  if (seconds <= 0) return "Le traitement démarre.";
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  const when =
    seconds < 60
      ? `${seconds} s`
      : `${minutes} min${rest ? ` ${String(rest).padStart(2, "0")}` : ""}`;
  const whom = present ? `avec ${present} ${present > 1 ? "présents" : "présent"}` : "sans présents";
  return `Le traitement démarre seul dans ${when}, ${whom}.`;
}

/** The people present from how many there were and those named (ADR 0069): the named ones
 *  count, the rest are unnamed; naming more than the count raises it. */
export function attendeesOf(
  count: number,
  ids: number[],
): { ids: number[]; count: number; unnamed: number | null } {
  const total = Math.max(count, ids.length, 0);
  const unnamed = total - ids.length;
  return { ids, count: total, unnamed: unnamed > 0 ? unnamed : null };
}
