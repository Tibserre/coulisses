/**
 * From the engine's attributed transcript to what the review screen shows: one row per
 * turn, untranscribed stretches in between, speakers numbered by order of appearance.
 * Times are the engine's, measured or absent: nothing here estimates one (P2).
 */
import type { AttributedTranscript, AttributedWord } from "./api.ts";

export interface SpeakerInfo {
  /** The engine's opaque label, stable within one run. */
  label: string | null;
  /** « Locuteur N », numbered by order of appearance; no name before step 2. */
  name: string;
  number: number | null;
  seconds: number;
  turns: number;
}

export interface TurnRow {
  kind: "turn";
  key: string;
  index: number;
  speaker: SpeakerInfo;
  start: number | null;
  end: number | null;
  words: AttributedWord[];
  /** Index of each word in the transcript, for the current-word lookup. */
  firstWord: number;
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
  speakers: SpeakerInfo[];
  /** Turn rows with a measured start, sorted, for finding the turn being heard. */
  timed: TurnRow[];
  wordCount: number;
  timedShare: number;
}

const UNKNOWN: SpeakerInfo = {
  label: null,
  name: "Locuteur inconnu",
  number: null,
  seconds: 0,
  turns: 0,
};

export function buildModel(t: AttributedTranscript): ReviewModel {
  const byLabel = new Map<string, SpeakerInfo>();
  const unknown = { ...UNKNOWN };
  const turnRows: TurnRow[] = t.turns.map((turn, index) => {
    let speaker = unknown;
    if (turn.speaker != null) {
      speaker = byLabel.get(turn.speaker) ?? {
        label: turn.speaker,
        name: `Locuteur ${byLabel.size + 1}`,
        number: byLabel.size + 1,
        seconds: 0,
        turns: 0,
      };
      byLabel.set(turn.speaker, speaker);
    }
    speaker.turns += 1;
    if (turn.start != null && turn.end != null)
      speaker.seconds += turn.end - turn.start;
    return {
      kind: "turn",
      key: `t${index}`,
      index,
      speaker,
      start: turn.start,
      end: turn.end,
      words: t.words.slice(turn.first_word, turn.end_word),
      firstWord: turn.first_word,
    };
  });

  const gaps: GapRow[] = t.untranscribed.map((g, i) => ({
    kind: "untranscribed",
    key: `g${i}`,
    start: g.start,
    end: g.end,
  }));
  // Gaps go before the first turn that starts after them; turns without a time keep
  // their place in the engine's order.
  const rows: Row[] = [];
  let g = 0;
  for (const row of turnRows) {
    while (g < gaps.length && row.start != null && gaps[g].start <= row.start)
      rows.push(gaps[g++]);
    rows.push(row);
  }
  while (g < gaps.length) rows.push(gaps[g++]);

  const speakers = [...byLabel.values()];
  if (unknown.turns > 0) speakers.push(unknown);
  const timedWords = t.words.filter((w) => w.start != null).length;
  return {
    rows,
    speakers,
    timed: turnRows.filter((r) => r.start != null),
    wordCount: t.words.length,
    timedShare: t.words.length ? timedWords / t.words.length : 0,
  };
}

/** The turn being heard at `time`: the last one that started before it. */
export function turnAt(model: ReviewModel, time: number): TurnRow | null {
  const timed = model.timed;
  let lo = 0;
  let hi = timed.length - 1;
  let found: TurnRow | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if ((timed[mid].start ?? 0) <= time) {
      found = timed[mid];
      lo = mid + 1;
    } else hi = mid - 1;
  }
  if (found && found.end != null && time > found.end + 1.5) return null; // in a silence
  return found;
}

/** Index (within the turn) of the measured word being said at `time`, or -1. Words
 *  without a measured time are never highlighted. */
export function wordAt(row: TurnRow, time: number): number {
  let current = -1;
  row.words.forEach((w, i) => {
    if (w.start != null && w.start <= time) current = i;
  });
  return current;
}
