// Run with `npm test` (Node's own test runner, no extra dependency).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { AttributedTranscript, AttributedWord } from "./api.ts";
import { buildModel, turnAt, wordAt, type TurnRow } from "./transcript.ts";

function word(
  text: string,
  start: number | null,
  speaker: string | null,
): AttributedWord {
  return {
    text,
    start,
    end: start == null ? null : start + 0.3,
    confidence: null,
    speakers: speaker ? [speaker] : [],
    speaker,
    uncertain: false,
  };
}

const TRANSCRIPT: AttributedTranscript = {
  run_id: "attribute-1",
  reference_source: "ref",
  language: "fr",
  words: [
    word("bonjour", 0.0, "SPEAKER_07"),
    word("à", 0.4, "SPEAKER_07"),
    word("tous", 0.6, "SPEAKER_07"),
    word("oui", 5.0, "SPEAKER_02"),
    word("sans", null, "SPEAKER_02"),
    word("temps", 5.8, "SPEAKER_02"),
    word("encore", 9.0, "SPEAKER_07"),
  ],
  turns: [
    { speaker: "SPEAKER_07", first_word: 0, end_word: 3, start: 0.0, end: 0.9 },
    { speaker: "SPEAKER_02", first_word: 3, end_word: 6, start: 5.0, end: 6.1 },
    { speaker: "SPEAKER_07", first_word: 6, end_word: 7, start: 9.0, end: 9.3 },
  ],
  speakers: ["SPEAKER_02", "SPEAKER_07"],
  untranscribed: [{ start: 2.0, end: 4.0, reason: "decoding loop" }],
};

test("speakers are numbered by order of appearance, not by the engine's label", () => {
  const model = buildModel(TRANSCRIPT);
  assert.deepEqual(
    model.speakers.map((s) => [s.label, s.name]),
    [
      ["SPEAKER_07", "Locuteur 1"],
      ["SPEAKER_02", "Locuteur 2"],
    ],
  );
  assert.equal(model.speakers[0].turns, 2);
});

test("an untranscribed stretch sits between the turns around it", () => {
  const kinds = buildModel(TRANSCRIPT).rows.map((r) => r.kind);
  assert.deepEqual(kinds, ["turn", "untranscribed", "turn", "turn"]);
});

test("the share of timed words counts only measured times", () => {
  assert.equal(buildModel(TRANSCRIPT).timedShare, 6 / 7);
});

test("the turn heard is the last one started, none in a long silence", () => {
  const model = buildModel(TRANSCRIPT);
  assert.equal(turnAt(model, 0.5)?.index, 0);
  assert.equal(turnAt(model, 5.2)?.index, 1);
  assert.equal(turnAt(model, 3.5), null);
});

test("a word without a measured time is never the current word (P2)", () => {
  const row = buildModel(TRANSCRIPT).rows[2] as TurnRow;
  assert.equal(row.words[1].text, "sans");
  assert.equal(wordAt(row, 5.5), 0); // still "oui": "sans" has no time to be placed at
  assert.equal(wordAt(row, 5.9), 2);
});
