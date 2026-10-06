// Run with `npm test` (Node's own test runner, no extra dependency).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CorrectedView, Speaker, Word } from "./api.ts";
import {
  buildModel,
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
    confidence: null,
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
  other_run_edits: 0,
  word_count: 7,
  timed_share: 6 / 7,
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

