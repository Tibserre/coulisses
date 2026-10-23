// Run with `npm test` (Node's own test runner, no extra dependency).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CorrectedView, Person, Speaker, Word } from "./api.ts";
import {
  changesChapters,
  choiceNote,
  namingChoices,
  voiceTurns,
  voicesToName,
  chaptersWriting,
  stripLayout,
  buildModel,
  phaseSpans,
  phaseOf,
  isDoubtful,
  wordTip,
  liveEditsKey,
  speakerTitle,
  toggleSelection,
  turnAt,
  wordAt,
  type TurnRow,
} from "./transcript.ts";

function word(text: string, start: number | null): Word {
  return {
    text,
    start,
    end: start == null ? null : start + 0.3,
    asr_confidence: null,
    uncertain: false,
    corrected: false,
    added: start == null,
    suggestion: null,
  };
}

function speaker(
  label: string,
  name: string,
  extra: Partial<Speaker> = {},
): Speaker {
  return {
    label,
    number: null,
    name,
    named: false,
    person_id: null,
    character: null,
    played_by: null,
    color_slot: null,
    seconds: 0,
    turns: 0,
    ...extra,
  };
}

const VIEW: CorrectedView = {
  run_id: "attribute-1",
  turns: [
    {
      index: 0,
      speaker: "7",
      start: 0.0,
      end: 0.9,
      edited: false,
      words: [word("bonjour", 0), word("à", 0.4), word("tous", 0.6)],
    },
    {
      index: 1,
      speaker: "2",
      start: 5.0,
      end: 6.1,
      edited: true,
      words: [word("oui", 5.0), word("sans", null), word("temps", 5.8)],
    },
    {
      index: 2,
      speaker: "7",
      start: 9.0,
      end: 9.3,
      edited: false,
      words: [word("encore", 9.0)],
    },
  ],
  speakers: [
    speaker("7", "Locuteur 1"),
    speaker("2", "Marie", { named: true, color_slot: 3 }),
  ],
  untranscribed: [{ start: 2.0, end: 4.0 }],
  edits: [],
  carryover: null,
  word_count: 7,
  timed_share: 6 / 7,
  phases: [],
  phases_run_id: null,
  phases_problem: null,
  markers: [],
  timed_notes: [],
  phases_by_markers: [],
};

/** The same, cut into two chapters: the first line, then the last two. */
const CHAPTERED: CorrectedView = {
  ...VIEW,
  phases: [
    {
      turn: 0,
      end_turn: 1,
      start: 0,
      end: 0.9,
      kind: "discussion",
      title: "Accueil",
      edited: false,
      marked: false,
    },
    {
      turn: 1,
      end_turn: 3,
      start: 5,
      end: 9.3,
      kind: "scene",
      title: "Le marché",
      edited: false,
      marked: false,
    },
  ],
  phases_run_id: "segment_phases-1",
};

test("each line carries its voice from the corrected view", () => {
  const model = buildModel(VIEW);
  const names = model.rows
    .filter((r): r is TurnRow => r.kind === "turn")
    .map((r) => r.speaker.name);
  assert.deepEqual(names, ["Locuteur 1", "Marie", "Locuteur 1"]);
});

test("an untranscribed stretch sits between the lines around it", () => {
  const kinds = buildModel(VIEW).rows.map((r) => r.kind);
  assert.deepEqual(kinds, ["turn", "untranscribed", "turn", "turn"]);
});

test("the line heard is the last one started, none in a long silence", () => {
  const model = buildModel(VIEW);
  assert.equal(turnAt(model, 0.5)?.turn.index, 0);
  assert.equal(turnAt(model, 5.2)?.turn.index, 1);
  assert.equal(turnAt(model, 3.5), null);
});

test("a word without a measured time is never the current word (P2)", () => {
  const row = buildModel(VIEW).rows[2] as TurnRow;
  assert.equal(row.turn.words[1].text, "sans");
  assert.equal(wordAt(row, 5.5), 0); // still "oui": "sans" has no time to be placed at
  assert.equal(wordAt(row, 5.9), 2);
});

test("a character shows who plays it", () => {
  assert.equal(
    speakerTitle(
      speaker("4", "Le marchand", { played_by: "Marie", named: true }),
    ),
    "Le marchand · joué par Marie",
  );
});

test("a click selects one line, Shift-click the whole range", () => {
  const order = [0, 1, 2, 3, 4];
  const one = toggleSelection(new Set(), order, 1, null);
  assert.deepEqual([...one], [1]);
  const range = toggleSelection(one, order, 3, 1);
  assert.deepEqual([...range].sort(), [1, 2, 3]);
  assert.deepEqual([...toggleSelection(range, order, 2, null)].sort(), [1, 3]);
});

test("the staleness key follows corrections, undo, redo and a new run", () => {
  const edit = (id: number, reverted = false) => ({
    id,
    kind: "edit_text",
    description: "",
    created_at: "",
    reverted,
    undone_by: null,
    redone: false,
    turn: 0,
  });
  const before = liveEditsKey({ run_id: "r1", edits: [edit(1)] });
  const corrected = liveEditsKey({ run_id: "r1", edits: [edit(1), edit(2)] });
  const undone = liveEditsKey({
    run_id: "r1",
    edits: [edit(1), edit(2, true)],
  });
  const redone = liveEditsKey({
    run_id: "r1",
    edits: [edit(1), edit(2, true), edit(4)],
  });
  const rerun = liveEditsKey({ run_id: "r2", edits: [edit(1)] });
  assert.notEqual(corrected, before);
  assert.equal(undone, before);
  assert.notEqual(undone, corrected);
  assert.notEqual(redone, corrected);
  assert.notEqual(rerun, before);
});

test("a word is underlined only when the transcription model doubted it (below 0.3)", () => {
  assert.equal(isDoubtful({ asr_confidence: 0.29 }), true);
  assert.equal(isDoubtful({ asr_confidence: 0.3 }), false);
  assert.equal(isDoubtful({ asr_confidence: null }), false); // runs before engine v1.4.0
  const tip = wordTip({ asr_confidence: 0.18, added: false, suggestion: null });
  assert.equal(tip?.kind, "confidence");
  assert.equal(tip?.percent, 18);
  assert.match(tip?.label ?? "", /^Le modèle doutait/);
  assert.equal(
    wordTip({ asr_confidence: 0.9, added: false, suggestion: null }),
    null,
  );
  assert.equal(
    wordTip({ asr_confidence: 0.1, added: false, suggestion: "Kathy" })?.kind,
    "suggestion",
  );
});

test("a heading opens each chapter, before its first line", () => {
  const rows = buildModel(CHAPTERED).rows.map((r) =>
    r.kind === "phase" ? `c${r.number}` : r.kind,
  );
  // The untranscribed stretch (2–4 s) ends the first chapter.
  assert.deepEqual(rows, ["c1", "turn", "untranscribed", "c2", "turn", "turn"]);
  const headings = buildModel(CHAPTERED).rows.filter((r) => r.kind === "phase");
  // Only the chapter that opens the session keeps its cut.
  assert.deepEqual(
    headings.map((r) => r.kind === "phase" && r.opensSession),
    [true, false],
  );
});

test("a folded chapter shows its heading only", () => {
  const rows = buildModel(CHAPTERED, new Set([1])).rows;
  assert.deepEqual(
    rows.map((r) => r.kind),
    ["phase", "turn", "untranscribed", "phase"],
  );
  const folded = rows.at(-1);
  assert.ok(folded?.kind === "phase" && folded.folded);
  // The folded lines are still found by time (the page keeps the one heard open).
  assert.equal(turnAt(buildModel(CHAPTERED, new Set([1])), 9.1)?.turn.index, 2);
});

test("a line belongs to the chapter that covers it", () => {
  assert.equal(phaseOf(CHAPTERED.phases, 2)?.title, "Le marché");
  assert.equal(phaseOf(VIEW.phases, 2), null);
});

test("the strip gives each chapter its stretch, the last one to the end", () => {
  const spans = phaseSpans(CHAPTERED, 12);
  assert.deepEqual(
    spans.map((s) => [s.number, s.start, s.end]),
    [
      [1, 0, 5],
      [2, 5, 12],
    ],
  );
});

test("a chapter whose first line has no time starts at its first timed line", () => {
  const view: CorrectedView = {
    ...CHAPTERED,
    turns: CHAPTERED.turns.map((t) =>
      t.index === 1 ? { ...t, start: null } : t,
    ),
    phases: CHAPTERED.phases.map((p) =>
      p.turn === 1 ? { ...p, start: null } : p,
    ),
  };
  assert.deepEqual(
    phaseSpans(view, 12).map((s) => s.start),
    [0, 9],
  );
});

test("a new detection changes the summary's staleness key", () => {
  assert.notEqual(liveEditsKey(VIEW), liveEditsKey(CHAPTERED));
});

test("key moments and notes from the recording sit between the lines, by time", () => {
  const view: CorrectedView = {
    ...VIEW,
    markers: [
      { id: 1, kind: "key_moment", at_s: 4.5 },
      { id: 2, kind: "scene", at_s: 0 },
    ],
    timed_notes: [{ id: 1, at_s: 8, text: "Belle écoute" }],
  };
  const rows = buildModel(view).rows.map((r) => r.kind);
  // 0:00 line, 2–4 s untranscribed, the moment at 4.5 s, 5 s line, the note at 8 s, 9 s line.
  assert.deepEqual(rows, [
    "turn",
    "untranscribed",
    "moment",
    "turn",
    "note",
    "turn",
  ]);
});

test("the same voice going on is not named again; anything between names it again", () => {
  const turn = (index: number, speaker: string, start: number) => ({
    index,
    speaker,
    start,
    end: start + 1,
    edited: false,
    words: [word("mot", start)],
  });
  const view: CorrectedView = {
    ...VIEW,
    turns: [
      turn(0, "7", 0),
      turn(1, "7", 2),
      turn(2, "2", 4),
      turn(3, "2", 6),
      turn(4, "2", 30),
    ],
    untranscribed: [{ start: 20, end: 25 }],
  };
  const lines = buildModel(view).rows.filter(
    (r): r is TurnRow => r.kind === "turn",
  );
  assert.deepEqual(
    lines.map((r) => !!r.continued),
    [false, true, false, true, false], // the stretch not transcribed, between 3 and 4
  );
});

test("a chapter, a key moment or a note between two lines of a voice names it again", () => {
  const turn = (index: number, speaker: string | null, start: number) => ({
    index,
    speaker,
    start,
    end: start + 1,
    edited: false,
    words: [word("mot", start)],
  });
  const view: CorrectedView = {
    ...VIEW,
    turns: [
      turn(0, "7", 0),
      turn(1, "7", 2), // a chapter starts here
      turn(2, "7", 4),
      turn(3, "7", 10), // a note at 8 s before it
      turn(4, null, 12),
      turn(5, null, 14), // no voice: never « continued »
    ],
    untranscribed: [],
    phases: [{ ...CHAPTERED.phases[0], turn: 1, end_turn: 6 }],
    markers: [],
    timed_notes: [{ id: 1, at_s: 8, text: "une idée" }],
  };
  const lines = buildModel(view).rows.filter(
    (r): r is TurnRow => r.kind === "turn",
  );
  assert.deepEqual(
    lines.map((r) => !!r.continued),
    [false, false, true, false, false, false],
  );
});

test("naming a voice offers the people matching what is typed, then a guest or a free name", async () => {
  const { nameChoices } = await import("./transcript.ts");
  const person = (id: number, name: string, archived = false) =>
    ({
      id,
      space_id: 1,
      kind: "member",
      name,
      role: null,
      color_slot: id,
      archived,
    }) as const;
  const people = [
    person(1, "Elise"),
    person(2, "Nathalie"),
    person(3, "Lucie", true),
  ];
  const voice = (label: string | null, name: string) =>
    ({ label, name }) as unknown as Speaker;
  const me = voice("SPEAKER_01", "Nouvelle voix 1");
  const voices = [me, voice("SPEAKER_02", "Elise"), voice(null, "Sans voix")];
  const kinds = (c: { kind: string }[]) => c.map((x) => x.kind);

  assert.deepEqual(kinds(nameChoices("who", me, people, voices, "")), [
    "person",
    "person",
  ]); // archived left out
  // A part of a name: the people it matches first, and still a new name.
  assert.deepEqual(kinds(nameChoices("who", me, people, voices, "nath")), [
    "person",
    "guest",
    "free",
  ]);
  assert.deepEqual(kinds(nameChoices("who", me, people, voices, " elise ")), [
    "person",
  ]); // the exact name: no guest
  assert.deepEqual(nameChoices("who", me, people, voices, "  Lu  cie "), [
    { kind: "guest", name: "Lu cie" },
    { kind: "free", name: "Lu cie" },
  ]);
  // Who plays a character: everyone, whatever was typed on the first view.
  assert.equal(nameChoices("character", me, people, voices, "nath").length, 2);
  // The same as another voice: never itself, never a line without a voice.
  assert.deepEqual(kinds(nameChoices("same", me, people, voices, "")), [
    "voice",
  ]);
  // A line without a voice: nothing to name.
  assert.deepEqual(
    nameChoices("who", voice(null, "?"), people, voices, "Lucie"),
    [],
  );
});

test("the person whose voice it seems to be comes first, typed or not", async () => {
  const { nameChoices } = await import("./transcript.ts");
  const person = (id: number, name: string) =>
    ({
      id,
      space_id: 1,
      kind: "member",
      name,
      role: null,
      color_slot: id,
      archived: false,
    }) as const;
  const people = [person(1, "Elise"), person(2, "Elodie"), person(3, "Marie")];
  const me = {
    label: "S1",
    name: "Locuteur 1",
    proposal: { person_id: 2, name: "Elodie", color_slot: 2, distance: 0.1 },
  } as unknown as Speaker;
  const ids = (c: { kind: string; person?: { id: number } }[]) =>
    c.map((x) => x.person?.id);
  assert.deepEqual(ids(nameChoices("who", me, people, [me], "")), [2, 1, 3]);
  assert.deepEqual(ids(nameChoices("who", me, people, [me], "el")), [
    2,
    1,
    undefined,
    undefined,
  ]);
  // Who plays a character: no proposal there.
  assert.deepEqual(
    ids(nameChoices("character", me, people, [me], "")),
    [1, 2, 3],
  );
});

test("one voice shown: its lines, its chapters, the others folded into a count", async () => {
  const { focusModel, speakerMarks, speakerExcerpt } =
    await import("./transcript.ts");
  const model = buildModel(CHAPTERED);
  const shape = (
    rows: { kind: string; count?: number; continued?: boolean }[],
  ) =>
    rows.map((r) =>
      r.kind === "others"
        ? `+${r.count}`
        : r.kind === "turn" && r.continued
          ? "turn…"
          : r.kind,
    );

  const marie = focusModel(model, "2");
  // Its chapter only (« Accueil » has none of its lines); the line of the other voice
  // before the chapter and the one after it, folded.
  assert.deepEqual(shape(marie.rows), ["+1", "phase", "turn", "+1"]);
  assert.deepEqual(
    marie.timed.map((r) => r.turn.index),
    [1],
  ); // the arrows stay within it

  const first = focusModel(model, "7");
  assert.deepEqual(shape(first.rows), ["phase", "turn", "phase", "+1", "turn"]); // its name said again after a fold

  assert.deepEqual(speakerMarks(model, "7"), [
    { start: 0, end: 0.9 },
    { start: 9, end: 9.3 },
  ]);
  assert.equal(speakerExcerpt(model, "7")?.turn.index, 0); // its longest line
  assert.equal(speakerExcerpt(model, "absent"), null);
});

test("chapters being written run over the session, the last one cut where reading stopped", () => {
  const phase = {
    turn: 0,
    end_turn: 1,
    start: 0,
    end: null,
    kind: "scene",
    title: "",
    edited: false,
    marked: false,
  } as const;
  const spans = [
    { phase, number: 1, start: 30, end: 600 },
    { phase, number: 2, start: 600, end: 3600 },
  ];
  const laid = stripLayout(spans, 3600, true, 900);
  assert.equal(laid.spans[1].end, 900);
  assert.equal(laid.lead, 30);
  assert.equal(laid.unread, 2700);
  assert.deepEqual([laid.from, laid.to], [0, 3600]);
  const set = stripLayout(spans, 3600, false, 900);
  assert.deepEqual([set.from, set.to, set.lead, set.unread], [30, 3600, 0, 0]);
});

test("what the strip says while the chapters are written", () => {
  const p = {
    step: "reading",
    part: 2,
    parts: 7,
    read_until: 1,
    checked: 0,
    to_check: 0,
    problem: null,
  } as const;
  assert.equal(
    chaptersWriting(p),
    "Les chapitres s'écrivent · partie 3 sur 7 · vous pouvez déjà relire",
  );
  assert.equal(
    chaptersWriting({ ...p, step: "checking", checked: 4, to_check: 5 }),
    "Les chapitres se vérifient · 5 sur 5",
  );
  assert.equal(
    chaptersWriting({ ...p, step: "checking", to_check: 0 }),
    "Les chapitres se vérifient",
  );
  assert.equal(
    chaptersWriting(null),
    "Les chapitres s'écrivent · vous pouvez déjà relire",
  );
  assert.equal(changesChapters({ kind: "set_phase" }), true);
  assert.equal(changesChapters({ kind: "edit_text" }), false);
});

test("the guided naming: voices in the order heard, the recognised person, then those present", () => {
  const people = [
    {
      id: 1,
      space_id: 1,
      kind: "member",
      name: "Ana",
      role: null,
      color_slot: 1,
      archived: false,
    },
    {
      id: 2,
      space_id: 1,
      kind: "member",
      name: "Bob",
      role: null,
      color_slot: 2,
      archived: false,
    },
    {
      id: 3,
      space_id: 1,
      kind: "member",
      name: "Cléo",
      role: null,
      color_slot: 3,
      archived: false,
    },
  ] as Person[];
  const v1 = speaker("1", "Voix 1", {
    proposal: { person_id: 3, name: "Cléo", color_slot: 3, distance: 0.1 },
  });
  const v2 = speaker("2", "Voix 2");
  const ana = speaker("3", "Ana", { named: true, person_id: 1 });
  const choices = namingChoices(v1, people, [v1, v2, ana], [1, 2], "");
  assert.deepEqual(
    choices.map((c) => (c.kind === "person" ? c.person.name : c.kind)),
    ["Cléo", "Bob", "Ana"],
  );
  assert.equal(choiceNote(choices[0], v1, [1, 2]), "voix reconnue");
  assert.equal(choiceNote(choices[1], v1, [1, 2]), "membre · présent");
  assert.equal(
    choiceNote(choices[2], v1, [1, 2], [v1, v2, ana]),
    "a déjà une voix : les réunir",
  );
  const typed = namingChoices(v2, people, [v1, v2], [], "Zoé");
  assert.deepEqual(
    typed.map((c) => c.kind),
    ["guest", "free"],
  );
});

test("voices to name come in the order first heard, with their own lines", () => {
  const line = (index: number, who: string) => ({
    index,
    speaker: who,
    start: index * 10,
    end: index * 10 + 2,
    edited: false,
    words: [word("mot", index * 10)],
  });
  const model = buildModel({
    ...VIEW,
    turns: [line(0, "2"), line(1, "1"), line(2, "2"), line(3, "3")],
    speakers: [
      speaker("1", "Voix 1"),
      speaker("2", "Voix 2"),
      speaker("3", "Marie", { named: true }),
    ],
    phases: [],
  });
  assert.deepEqual(
    voicesToName(model).map((s) => s.label),
    ["2", "1"],
  );
  assert.deepEqual(
    voiceTurns(model, "2").map((r) => r.turn.index),
    [0, 2],
  );
});
