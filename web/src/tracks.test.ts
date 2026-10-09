// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { AudioSource } from "./api.ts";
import { extraTracks } from "./tracks.ts";

const source = (source_id: string, over: Partial<AudioSource> = {}): AudioSource => ({
  source_id,
  origin: "captured",
  original_name: `${source_id}.wav`,
  file_name: `${source_id}.wav`,
  sha256: "",
  size_bytes: 1,
  duration_s: 60,
  sample_rate: 48000,
  channels: 1,
  codec: "pcm_s24le",
  file_present: true,
  capture_state: "complete",
  device: source_id === "mic2" ? "Micro de l'iPhone" : "Son de l'ordinateur",
  ...over,
});

test("nothing beside the reference: nothing said", () => {
  assert.equal(extraTracks([]), null);
});

test("the computer's sound is named, and said to be mixed in", () => {
  const said = extraTracks([source("system")]);
  assert.equal(said?.text, " · son de l'ordinateur");
  assert.match(said?.title ?? "", /réunis pour le traitement/);
});

test("a second microphone is counted, and said not processed yet", () => {
  const said = extraTracks([source("mic2")]);
  assert.equal(said?.text, " · 2 micros");
  assert.match(said?.title ?? "", /Micro de l'iPhone.*Seul le micro principal est traité/);
});

test("a computer's sound that stayed silent points to the permission", () => {
  const mix = { gain: 1, sha256: "", system_silent: true, made_at: "" };
  const said = extraTracks([source("system")], mix);
  assert.equal(said?.text, " · son de l'ordinateur resté muet");
  assert.match(said?.title ?? "", /Enregistrement de l'écran et de l'audio du système.*micro seul/);
});

test("a computer's sound with a faulty file says the microphone is processed alone", () => {
  const said = extraTracks([source("system", { duration_s: null })]);
  assert.equal(said?.text, " · son de l'ordinateur (piste illisible)");
  assert.match(said?.title ?? "", /micro seul est traité/);
});

test("several microphones added: each in trouble is named", () => {
  const said = extraTracks([
    source("mic2"),
    source("mic3", { device: "Micro USB", duration_s: 0 }),
  ]);
  assert.equal(said?.text, " · 3 micros (piste « Micro USB » vide)");
  assert.match(said?.title ?? "", /Gardés en plus : Micro de l'iPhone, Micro USB/);
});

test("both, each with what went wrong with its file", () => {
  const said = extraTracks([
    source("mic2", { duration_s: 0 }),
    source("system", { file_present: false }),
  ]);
  assert.equal(said?.text, " · son de l'ordinateur (piste introuvable) · 2 micros (piste « Micro de l'iPhone » vide)");
});
