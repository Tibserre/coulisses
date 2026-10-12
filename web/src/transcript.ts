/**
 * From the service's corrected view to what the review screen shows: one row per line,
 * untranscribed stretches in between, a heading at each chapter, each line with its voice.
 * Times are the engine's, measured or absent: nothing here estimates one (P2).
 */
import type { CorrectedView, Marker, Phase, PhaseKind, Speaker, TimedNote, Turn, Word } from "./api.ts";

export interface TurnRow {
  kind: "turn";
  key: string;
  turn: Turn;
  speaker: Speaker;
  /** The line just above is the same voice's, with nothing between: its name is not said
   *  again (the line keeps its time, its selection, its actions). */
  continued?: boolean;
}

export interface GapRow {
  kind: "untranscribed";
  key: string;
  start: number;
  end: number;
}

export interface PhaseRow {
  kind: "phase";
  key: string;
  phase: Phase;
  /** 1 for the first chapter. */
  number: number;
  folded: boolean;
  /** It starts at the session's first line: its cut cannot be removed. */
  opensSession: boolean;
}

/** A key moment marked while recording. */
export interface MomentRow {
  kind: "moment";
  key: string;
  start: number;
  marker: Marker;
}

/** A note taken while recording, where it was thought of. */
export interface NoteRow {
  kind: "note";
  key: string;
  start: number;
  note: TimedNote;
}

export type Row = TurnRow | GapRow | PhaseRow | MomentRow | NoteRow;

export interface ReviewModel {
  rows: Row[];
  speakers: Speaker[];
  phases: Phase[];
  /** Turn rows with a measured start, sorted, for finding the line being heard. */
  timed: TurnRow[];
  /** Speaker by label, for the lines. */
  speakerOf: Map<string | null, Speaker>;
}

const UNKNOWN: Speaker = {
  label: null,
  number: null,
  name: "Locuteur inconnu",
  named: false,
  person_id: null,
  character: null,
  played_by: null,
  color_slot: null,
  seconds: 0,
  turns: 0,
};

/** How a chapter's kind is said in the interface. */
export const KIND_LABEL: Record<PhaseKind, string> = {
  scene: "Jeu",
  discussion: "Discussion",
  other: "Autre",
};

/** The chapter a line belongs to, if any. */
export function phaseOf(phases: readonly Phase[], turn: number): Phase | null {
  return phases.find((p) => p.turn <= turn && turn < p.end_turn) ?? null;
}

/** `folded`: first lines of the chapters shown folded (their lines are left out). */
export function buildModel(view: CorrectedView, folded: ReadonlySet<number> = new Set()): ReviewModel {
  const speakerOf = new Map<string | null, Speaker>(
    view.speakers.map((s) => [s.label, s]),
  );
  const turnRows: TurnRow[] = view.turns.map((turn) => ({
    kind: "turn",
    key: `t${turn.index}`,
    turn,
    speaker: speakerOf.get(turn.speaker) ?? UNKNOWN,
  }));
  // Rows placed by time between the lines: untranscribed stretches, key moments, notes.
  const gaps: (GapRow | MomentRow | NoteRow)[] = [
    ...view.untranscribed.map((g, i): GapRow => ({
      kind: "untranscribed",
      key: `g${i}`,
      start: g.start,
      end: g.end,
    })),
    ...(view.markers ?? [])
      .filter((m) => m.kind === "key_moment")
      .map((m): MomentRow => ({ kind: "moment", key: `m${m.id}`, start: m.at_s, marker: m })),
    ...(view.timed_notes ?? []).map(
      (n): NoteRow => ({ kind: "note", key: `n${n.id}`, start: n.at_s, note: n }),
    ),
  ].sort((a, b) => a.start - b.start);
  const phases = view.phases ?? [];
  const startOf = new Map(phases.map((p, i) => [p.turn, { phase: p, number: i + 1 }]));
  // Gaps go before the first line that starts after them; lines without a time keep
  // their place in the engine's order. A folded chapter shows its heading only.
  const rows: Row[] = [];
  let g = 0;
  let hidden = false;
  for (const row of turnRows) {
    while (
      g < gaps.length &&
      row.turn.start != null &&
      gaps[g].start <= row.turn.start
    ) {
      const gap = gaps[g++];
      if (!hidden) rows.push(gap);
    }
    const starts = startOf.get(row.turn.index);
    if (starts) {
      hidden = folded.has(starts.phase.turn);
      rows.push({
        kind: "phase",
        key: `c${starts.phase.turn}`,
        phase: starts.phase,
        number: starts.number,
        folded: hidden,
        opensSession: starts.phase.turn === view.turns[0]?.index,
      });
    }
    if (!hidden) {
      const above = rows[rows.length - 1];
      const continued =
        above?.kind === "turn" && above.turn.speaker === row.turn.speaker && row.speaker.label !== null;
      rows.push(continued ? { ...row, continued } : row);
    }
  }
  while (g < gaps.length) {
    const gap = gaps[g++];
    if (!hidden) rows.push(gap);
  }
  return {
    rows,
    speakers: view.speakers,
    phases,
    timed: turnRows.filter((r) => r.turn.start != null),
    speakerOf,
  };
}

/** The line being heard at `time`: the last one that started before it. */
export function turnAt(model: ReviewModel, time: number): TurnRow | null {
  const timed = model.timed;
  let lo = 0;
  let hi = timed.length - 1;
  let found: TurnRow | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if ((timed[mid].turn.start ?? 0) <= time) {
      found = timed[mid];
      lo = mid + 1;
    } else hi = mid - 1;
  }
  if (found && found.turn.end != null && time > found.turn.end + 1.5)
    return null; // silence
  return found;
}

/** Index (within the line) of the measured word being said at `time`, or -1. Words
 *  without a measured time are never highlighted. */
export function wordAt(row: TurnRow, time: number): number {
  let current = -1;
  row.turn.words.forEach((w, i) => {
    if (w.start != null && w.start <= time) current = i;
  });
  return current;
}

/** The display name of a voice: a character shows who plays it. */
export function speakerTitle(speaker: Speaker): string {
  return speaker.played_by
    ? `${speaker.name} · joué par ${speaker.played_by}`
    : speaker.name;
}

/** Lines selected after a click: alone, or the whole range from the last clicked line
 *  (with Shift), in the order of the transcript. */
export function toggleSelection(
  selected: ReadonlySet<number>,
  order: readonly number[],
  turn: number,
  extendFrom: number | null,
): Set<number> {
  const next = new Set(selected);
  if (extendFrom != null && order.includes(extendFrom) && order.includes(turn)) {
    const [a, b] = [order.indexOf(extendFrom), order.indexOf(turn)].sort((x, y) => x - y);
    for (const index of order.slice(a, b + 1)) next.add(index);
  } else if (next.has(turn)) next.delete(turn);
  else next.add(turn);
  return next;
}


/** What a summary's staleness depends on, built as the service compares it: the run, the
 *  corrections in force and the chapter detection. It changes on a correction, an undo, a
 *  redo and a new detection. */
export function liveEditsKey(
  view: Pick<CorrectedView, "run_id" | "edits"> & Partial<Pick<CorrectedView, "phases_run_id">>,
): string {
  const live = view.edits
    .filter((e) => !e.reverted)
    .map((e) => e.id)
    .sort((a, b) => a - b);
  return `${view.run_id}:${live.join(",")}:${view.phases_run_id ?? ""}`;
}

/** Below this, the transcription model doubted the word (engine README, « Scores par mot » :
 *  83 % of the words it marks are wrong, but it finds only some of the mistakes). */
export const DOUBTFUL_BELOW = 0.3;

export function isDoubtful(word: Pick<Word, "asr_confidence">): boolean {
  return word.asr_confidence != null && word.asr_confidence < DOUBTFUL_BELOW;
}

export interface WordTip {
  kind: "suggestion" | "added" | "confidence";
  text?: string;
  /** What screen readers get (aria-description). */
  label: string;
  percent?: number;
}

/** One tip per word, the most useful first: what to write, then how it was written, then
 *  that the model doubted (never « sure » for the rest: the score misses some mistakes). */
export function wordTip(word: Pick<Word, "asr_confidence" | "added" | "suggestion">): WordTip | null {
  if (word.suggestion)
    return { kind: "suggestion", text: `→ ${word.suggestion}`, label: `Peut-être « ${word.suggestion} »` };
  if (word.added) return { kind: "added", text: "ajouté", label: "Ajouté à la main, sans horodatage mesuré" };
  if (isDoubtful(word)) {
    const percent = Math.round((word.asr_confidence ?? 0) * 100);
    return { kind: "confidence", percent, label: `Le modèle doutait de ce mot (sûr à ${percent} %)` };
  }
  return null;
}

export interface PhaseSpan {
  phase: Phase;
  number: number;
  start: number;
  end: number;
}

/** Each chapter's stretch of the recording, for the strip: from its first measured line
 *  to the next chapter's (the last one to the end). A chapter none of whose lines has a
 *  time has no place on it. */
export function phaseSpans(view: Pick<CorrectedView, "phases" | "turns">, duration: number): PhaseSpan[] {
  const firsts = view.phases.map((p) => {
    if (p.start != null) return p.start;
    const timed = view.turns.slice(p.turn, p.end_turn).find((t) => t.start != null);
    return timed?.start ?? null;
  });
  const spans: PhaseSpan[] = [];
  view.phases.forEach((phase, i) => {
    const start = firsts[i];
    if (start == null) return;
    const next = firsts.slice(i + 1).find((s): s is number => s != null);
    spans.push({ phase, number: i + 1, start, end: Math.max(start, next ?? duration) });
  });
  return spans;
}
