/**
 * From the service's corrected view to what the review screen shows: one row per line,
 * untranscribed stretches in between, a heading at each chapter, each line with its voice.
 * Times are the engine's, measured or absent: nothing here estimates one (P2).
 */
import type {
  CorrectedView,
  Marker,
  Person,
  Phase,
  PhaseKind,
  PhasesSteps,
  Speaker,
  TimedNote,
  Turn,
  Word,
} from "./api.ts";

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

/** Showing one voice only: the lines of the others between two of its lines, folded into
 *  a count. */
export interface OthersRow {
  kind: "others";
  key: string;
  count: number;
}

export type Row = TurnRow | GapRow | PhaseRow | MomentRow | NoteRow | OthersRow;

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
export function buildModel(
  view: CorrectedView,
  folded: ReadonlySet<number> = new Set(),
): ReviewModel {
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
      .map((m): MomentRow => ({
        kind: "moment",
        key: `m${m.id}`,
        start: m.at_s,
        marker: m,
      })),
    ...(view.timed_notes ?? []).map((n): NoteRow => ({
      kind: "note",
      key: `n${n.id}`,
      start: n.at_s,
      note: n,
    })),
  ].sort((a, b) => a.start - b.start);
  const phases = view.phases ?? [];
  const startOf = new Map(
    phases.map((p, i) => [p.turn, { phase: p, number: i + 1 }]),
  );
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
        above?.kind === "turn" &&
        above.turn.speaker === row.turn.speaker &&
        row.speaker.label !== null;
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
  if (
    extendFrom != null &&
    order.includes(extendFrom) &&
    order.includes(turn)
  ) {
    const [a, b] = [order.indexOf(extendFrom), order.indexOf(turn)].sort(
      (x, y) => x - y,
    );
    for (const index of order.slice(a, b + 1)) next.add(index);
  } else if (next.has(turn)) next.delete(turn);
  else next.add(turn);
  return next;
}

/** What a summary's staleness depends on, built as the service compares it: the run, the
 *  corrections in force and the chapter detection. It changes on a correction, an undo, a
 *  redo and a new detection. */
export function liveEditsKey(
  view: Pick<CorrectedView, "run_id" | "edits"> &
    Partial<Pick<CorrectedView, "phases_run_id">>,
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
export function wordTip(
  word: Pick<Word, "asr_confidence" | "added" | "suggestion">,
): WordTip | null {
  if (word.suggestion)
    return {
      kind: "suggestion",
      text: `→ ${word.suggestion}`,
      label: `Peut-être « ${word.suggestion} »`,
    };
  if (word.added)
    return {
      kind: "added",
      text: "ajouté",
      label: "Ajouté à la main, sans horodatage mesuré",
    };
  if (isDoubtful(word)) {
    const percent = Math.round((word.asr_confidence ?? 0) * 100);
    return {
      kind: "confidence",
      percent,
      label: `Le modèle doutait de ce mot (sûr à ${percent} %)`,
    };
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
export function phaseSpans(
  view: Pick<CorrectedView, "phases" | "turns">,
  duration: number,
): PhaseSpan[] {
  const firsts = view.phases.map((p) => {
    if (p.start != null) return p.start;
    const timed = view.turns
      .slice(p.turn, p.end_turn)
      .find((t) => t.start != null);
    return timed?.start ?? null;
  });
  const spans: PhaseSpan[] = [];
  view.phases.forEach((phase, i) => {
    const start = firsts[i];
    if (start == null) return;
    const next = firsts.slice(i + 1).find((s): s is number => s != null);
    spans.push({
      phase,
      number: i + 1,
      start,
      end: Math.max(start, next ?? duration),
    });
  });
  return spans;
}

/** What naming a voice offers, by view: who it is (the people of the space matching what is
 *  typed, then, for a name not found, a new guest or a free name), who plays a character
 *  (every person, whatever was typed before), or another voice it is the same as. A line
 *  without a voice offers nothing: it is given to a voice instead. */
export type NameChoice =
  | { kind: "person"; person: Person }
  | { kind: "guest"; name: string }
  | { kind: "free"; name: string }
  | { kind: "voice"; voice: Speaker };

export function nameChoices(
  view: "who" | "character" | "same",
  speaker: Speaker,
  people: Person[],
  voices: Speaker[],
  typed: string,
): NameChoice[] {
  if (speaker.label === null) return [];
  const present = people.filter((p) => !p.archived);
  const name = typed.replace(/\s+/g, " ").trim();
  const q = name.toLowerCase();
  if (view === "character")
    return present.map((person) => ({ kind: "person", person }));
  if (view === "same")
    return voices
      .filter(
        (v) =>
          v.label !== null &&
          v.label !== speaker.label &&
          (!q || v.name.toLowerCase().includes(q)),
      )
      .map((voice) => ({ kind: "voice", voice }));
  // The person whose voice it seems to be comes first (ADR 0057).
  const proposed = speaker.proposal?.person_id;
  const matches: NameChoice[] = present
    .filter((p) => !q || p.name.toLowerCase().includes(q))
    .sort((a, b) => Number(b.id === proposed) - Number(a.id === proposed))
    .map((person) => ({ kind: "person", person }));
  if (!q || present.some((p) => p.name.toLowerCase() === q)) return matches;
  return [...matches, { kind: "guest", name }, { kind: "free", name }];
}

/** The transcript as it is when only one voice is shown: its lines, the chapters they are
 *  in, and between them how many lines of the other voices are left out. Its name is said
 *  again after each fold. Moving from line to line (the player's arrows) stays within it. */
export function focusModel(model: ReviewModel, label: string): ReviewModel {
  const rows: Row[] = [];
  let skipped = 0;
  const fold = () => {
    if (skipped)
      rows.push({ kind: "others", key: `o${rows.length}`, count: skipped });
    skipped = 0;
  };
  for (const row of model.rows) {
    if (row.kind === "turn") {
      if (row.speaker.label !== label) {
        skipped += 1;
        continue;
      }
      fold();
      const above = rows[rows.length - 1];
      rows.push({ ...row, continued: above?.kind === "turn" || undefined });
    } else if (row.kind === "phase") {
      fold();
      rows.push(row);
    }
  }
  fold();
  // A chapter with none of its lines says nothing here (read backwards: one pass).
  const kept: Row[] = [];
  let lineAfter = false;
  for (let i = rows.length - 1; i >= 0; i--) {
    const r = rows[i];
    if (r.kind === "turn") lineAfter = true;
    if (r.kind === "phase") {
      if (!lineAfter) continue;
      lineAfter = false;
    }
    const last = kept[kept.length - 1];
    if (r.kind === "others" && last?.kind === "others") last.count += r.count;
    else kept.push(r);
  }
  kept.reverse();
  return {
    ...model,
    rows: kept,
    timed: model.timed.filter((r) => r.speaker.label === label),
  };
}

/** Where a voice speaks, as stretches of the recording: measured times only (a line
 *  without a measured end is a point, drawn as a thin stroke; P2). */
export function speakerMarks(
  model: ReviewModel,
  label: string,
): { start: number; end: number }[] {
  return model.timed
    .filter((r) => r.speaker.label === label && r.turn.start != null)
    .map((r) => ({ start: r.turn.start!, end: r.turn.end ?? r.turn.start! }));
}

/** The line to hear to recognise a voice: its longest measured one. */
export function speakerExcerpt(
  model: ReviewModel,
  label: string,
): TurnRow | null {
  let best: TurnRow | null = null;
  let length = -1;
  for (const r of model.timed) {
    if (r.speaker.label !== label || r.turn.start == null || r.turn.end == null)
      continue;
    const l = r.turn.end - r.turn.start;
    if (l > length) {
      best = r;
      length = l;
    }
  }
  return best;
}

/** The strip of chapters laid out (ADR 0061). Set chapters run from the first one's start
 *  to the last one's end. Chapters being written run over the whole session: before the
 *  first one, room is kept (`lead`), and after `readUntil` (the last line the detection
 *  read, measured), nothing is known yet: the last chapter is cut there and the rest kept
 *  empty (`unread`). Nothing is made up (P2). */
export interface StripLayout {
  spans: PhaseSpan[];
  from: number;
  to: number;
  lead: number;
  unread: number;
}

export function stripLayout(
  spans: PhaseSpan[],
  duration: number,
  provisional: boolean,
  readUntil: number | null,
): StripLayout {
  if (!provisional) {
    const from = spans[0]?.start ?? 0;
    return {
      spans,
      from,
      to: Math.max(from + 1, ...spans.map((s) => s.end)),
      lead: 0,
      unread: 0,
    };
  }
  const cut =
    readUntil === null
      ? spans
      : spans.map((s) =>
          s.end > readUntil ? { ...s, end: Math.max(s.start, readUntil) } : s,
        );
  const to = Math.max(1, duration, ...cut.map((s) => s.end));
  const known = Math.max(0, ...cut.map((s) => s.end));
  return {
    spans: cut,
    from: 0,
    to,
    lead: cut[0]?.start ?? 0,
    unread: Math.max(0, to - known),
  };
}

/** What the strip says while the chapters are being written. */
export function chaptersWriting(
  progress: PhasesSteps | null | undefined,
): string {
  if (progress?.step === "checking")
    return progress.to_check > 0
      ? `Les chapitres se vérifient · ${Math.min(progress.checked + 1, progress.to_check)} sur ${progress.to_check}`
      : "Les chapitres se vérifient";
  if (progress && progress.parts > 1)
    return `Les chapitres s'écrivent · partie ${Math.min(progress.part + 1, progress.parts)} sur ${progress.parts} · vous pouvez déjà relire`;
  return "Les chapitres s'écrivent · vous pouvez déjà relire";
}

/** A correction that changes the chapters: refused while they are being written. */
export function changesChapters(correction: { kind: string }): boolean {
  return correction.kind === "set_phase" || correction.kind === "remove_phase";
}

/** The voices still without a name, in the order they are first heard: the guided naming
 *  goes through them one after the other. */
export function voicesToName(model: ReviewModel): Speaker[] {
  const seen: Speaker[] = [];
  for (const row of model.rows)
    if (
      row.kind === "turn" &&
      row.speaker.label !== null &&
      !row.speaker.named &&
      !seen.includes(row.speaker)
    )
      seen.push(row.speaker);
  return seen;
}

/** A voice's lines, in their order: what « réplique précédente / suivante » goes through. */
export function voiceTurns(model: ReviewModel, label: string): TurnRow[] {
  return model.rows.filter(
    (r): r is TurnRow => r.kind === "turn" && r.speaker.label === label,
  );
}

/** Who a voice may be, for the guided naming: the person whose voice it seems to be first
 *  (ADR 0057), then the people checked present who have no voice yet, then the others;
 *  a name typed and not found becomes a guest or a free name. */
export function namingChoices(
  speaker: Speaker,
  people: Person[],
  voices: Speaker[],
  attendees: readonly number[],
  typed: string,
): NameChoice[] {
  const choices = nameChoices("who", speaker, people, voices, typed);
  const proposed = speaker.proposal?.person_id;
  const voiced = new Set(
    voices.flatMap((v) =>
      v.person_id != null && v.named ? [v.person_id] : [],
    ),
  );
  const rank = (c: NameChoice) =>
    c.kind !== "person"
      ? 3
      : c.person.id === proposed
        ? 0
        : attendees.includes(c.person.id) && !voiced.has(c.person.id)
          ? 1
          : 2;
  return choices
    .map((c, i) => ({ c, i }))
    .sort((a, b) => rank(a.c) - rank(b.c) || a.i - b.i)
    .map(({ c }) => c);
}

/** What the guided naming says of a choice. */
export function choiceNote(
  c: NameChoice,
  speaker: Speaker,
  attendees: readonly number[],
  voices: readonly Speaker[] = [],
): string {
  if (c.kind === "guest") return "nouvel invité";
  if (c.kind === "free") return "nom libre";
  if (c.kind === "voice") return "même voix";
  if (c.person.id === speaker.proposal?.person_id) return "voix reconnue";
  // Naming it after them makes one voice of the two (the engine had split a person, P3).
  if (voices.some((v) => v.named && v.person_id === c.person.id))
    return "a déjà une voix : les réunir";
  const role =
    c.person.kind === "guest" ? "invité" : (c.person.role ?? "membre");
  return attendees.includes(c.person.id) ? `${role} · présent` : role;
}

/** A line's measured length in seconds, or null when its start or end was not measured. */
export function turnSeconds(turn: Turn): number | null {
  return turn.start != null && turn.end != null
    ? Math.max(0, turn.end - turn.start)
    : null;
}

/** A voice's lines as the guided naming lists them (ADR 0062): the longest first (where
 *  the voice is heard best; a line of unmeasured length last), or in their order. */
export function namingLines(
  lines: TurnRow[],
  order: "long" | "time",
): TurnRow[] {
  if (order === "time") return lines;
  return [...lines].sort(
    (a, b) => (turnSeconds(b.turn) ?? -1) - (turnSeconds(a.turn) ?? -1),
  );
}

/** On a voice's strip, the line whose measured start is nearest a time, among lines with
 *  a measured start. */
export function nearestLine(lines: TurnRow[], at: number): TurnRow | null {
  let best: TurnRow | null = null;
  for (const r of lines) {
    if (r.turn.start == null) continue;
    if (!best || Math.abs(r.turn.start - at) < Math.abs(best.turn.start! - at))
      best = r;
  }
  return best;
}

/** A line's mark on the strip, in pixels: as long as it lasts (half a pixel a second),
 *  3 at least, 14 at most; 3 when its length is not measured. */
export function tickWidth(turn: Turn): number {
  return Math.max(3, Math.min(14, (turnSeconds(turn) ?? 0) / 2));
}
