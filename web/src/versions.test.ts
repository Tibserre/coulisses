import assert from "node:assert/strict";
import { test } from "node:test";
import { carriedText, rerunMinutes, transcribeGain, versionOrigin } from "./versions.ts";

test("a version says what made it", () => {
  assert.equal(versionOrigin({ origin: "first", min_voices: 2 }), "premier traitement");
  assert.equal(versionOrigin({ origin: "transcribe", min_voices: 2 }), "transcription refaite");
  assert.equal(
    versionOrigin({ origin: "diarize", min_voices: 4 }),
    "voix séparées à nouveau (au moins 4)",
  );
});

test("the carried corrections are counted, the missing ones too", () => {
  assert.equal(carriedText({ carried: null, not_carried: null }), null);
  assert.equal(carriedText({ carried: 1, not_carried: 0 }), "1 correction reportée");
  assert.equal(
    carriedText({ carried: 12, not_carried: 2 }),
    "12 corrections reportées, 2 à reprendre",
  );
});

test("a rerun's time is the one measured last time, else an estimate from the audio", () => {
  const facts = { transcribe_s: 540, diarize_s: null };
  assert.deepEqual(rerunMinutes(facts, "transcribe", 5400), { minutes: 9, measured: true });
  assert.deepEqual(rerunMinutes(facts, "diarize", 5400), { minutes: 15, measured: false });
  assert.equal(rerunMinutes(facts, "diarize", null), null);
});

test("a transcription rerun says what it brings, or that nothing changed", () => {
  assert.match(
    transcribeGain({ glossary_added: ["Kathy", "catch"], engine_updated: false }),
    /^2 termes ajoutés au glossaire depuis la dernière fois \(Kathy, catch\)\.$/,
  );
  assert.match(
    transcribeGain({ glossary_added: ["a", "b", "c", "d", "e", "f"], engine_updated: true }),
    /\(a, b, c, d, et 2 de plus\) ; le moteur de transcription a été mis à jour depuis\.$/,
  );
  assert.match(transcribeGain({ glossary_added: [], engine_updated: false }), /^Rien n'a changé/);
});
