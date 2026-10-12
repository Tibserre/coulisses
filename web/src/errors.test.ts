import assert from "node:assert/strict";
import { test } from "node:test";
import { describeStageError, friendlyError } from "./errors.ts";

test("no error, no message", () => {
  assert.equal(friendlyError(null), null);
});

test("the engine's own error types are said in plain French", () => {
  assert.match(friendlyError("Interrupted : caller stopped")!, /^Interrompue/);
  assert.equal(friendlyError("Cancelled : cancel()"), "Annulée.");
  assert.match(friendlyError("ChildCrash : child exited with code -9")!, /mémoire/);
  assert.match(friendlyError("ApplicationStoppingError : align non lancée")!, /s'arrêtait/);
  assert.match(friendlyError("Exécution x : le moteur refuse de la clore (vivant)")!, /encore tourner/);
  assert.equal(friendlyError("Interrompue avant d'avoir démarré"), "Interrompue avant d'avoir démarré.");
});

test("an unknown error is still shown, never swallowed (P8)", () => {
  assert.match(friendlyError("RuntimeError : DiariZen failed (exit code 1)")!, /a échoué/);
});

test("each engine code gets its own explanation", () => {
  const codes = [
    "model_missing",
    "model_altered",
    "environment_missing",
    "audio_unreadable",
    "too_few_speakers",
    "out_of_memory",
    "interrupted",
    "cancelled",
    "scratch_not_cleared",
    "engine_failed",
  ] as const;
  const texts = codes.map((code) =>
    describeStageError({ error: "x", error_code: code, error_details: {} }),
  );
  assert.equal(new Set(texts).size, codes.length);
});

test("the details of a code are woven into its message", () => {
  const tooFew = describeStageError({
    error: "RuntimeError : found 3 speakers, expected 5",
    error_code: "too_few_speakers",
    error_details: { found: 3, expected: 5 },
  });
  assert.match(tooFew!, /^3 voix trouvées pour 5 présents/);
  const missing = describeStageError({
    error: "x",
    error_code: "model_missing",
    error_details: { model: "qwen3-asr-1.7b" },
  });
  assert.match(missing!, /\(qwen3-asr-1\.7b\)\. Téléchargez-le dans Réglages, onglet Transcription/);
});

test("without a code, the older text matching still applies", () => {
  const old = describeStageError({ error: "Interrupted : stop", error_code: null, error_details: null });
  assert.match(old!, /^Interrompue/);
});
