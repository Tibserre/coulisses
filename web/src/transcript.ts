/**
 * From the service's corrected view to what the review screen shows: one row per line,
 * untranscribed stretches in between, each line with its voice. Times are the engine's,
 * measured or absent: nothing here estimates one (P2).
 */
import type { CorrectedView, Speaker, Turn } from "./api.ts";

export interface TurnRow {
  kind: "turn";
  key: string;
  turn: Turn;
  speaker: Speaker;
}

export interface GapRow {
  kind: "untranscribed";
  key: string;
  start: number;
  end: number;
}

export type Row = TurnRow | GapRow;

export interface ReviewModel {
  rows: Row[];
  speakers: Speaker[];
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

export function buildModel(view: CorrectedView): ReviewModel {
  const speakerOf = new Map<string | null, Speaker>(
    view.speakers.map((s) => [s.label, s]),
  );
  const turnRows: TurnRow[] = view.turns.map((turn) => ({
    kind: "turn",
    key: `t${turn.index}`,
    turn,
    speaker: speakerOf.get(turn.speaker) ?? UNKNOWN,
  }));
  const gaps: GapRow[] = view.untranscribed.map((g, i) => ({
    kind: "untranscribed",
    key: `g${i}`,
    start: g.start,
    end: g.end,
  }));
  // Gaps go before the first line that starts after them; lines without a time keep
  // their place in the engine's order.
  const rows: Row[] = [];
  let g = 0;
  for (const row of turnRows) {
    while (
      g < gaps.length &&
      row.turn.start != null &&
      gaps[g].start <= row.turn.start
    )
      rows.push(gaps[g++]);
    rows.push(row);
  }
  while (g < gaps.length) rows.push(gaps[g++]);
  return {
    rows,
    speakers: view.speakers,
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

