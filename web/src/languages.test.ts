// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Language, ModelAction, ProcessingWait } from "./api.ts";
import {
  canRemoveLanguage,
  languageCards,
  languageSize,
  offersRemoval,
  inLanguage,
  languageNote,
  languageState,
  languageUses,
  languageWorthShowing,
  rerunLanguageMissing,
  theLanguage,
  versionLanguage,
  waitWords,
} from "./languages.ts";

const language = (over: Partial<Language>): Language => ({
  language: "en",
  label: "Anglais",
  installed: false,
  missing_models: ["wav2vec2-ctc-english"],
  download_bytes: 1_260_000_000,
  models: ["asr", "wav2vec2-ctc-english"],
  own_models: ["wav2vec2-ctc-english"],
  downloads: [],
  used_by: { spaces: [], waiting_sessions: [] },
  ...over,
});

const french = language({
  language: "fr",
  label: "Français",
  installed: true,
  missing_models: [],
  download_bytes: 0,
  own_models: [],
});

const action = (over: Partial<ModelAction>): ModelAction => ({
  kind: "model",
  name: "wav2vec2-ctc-english",
  state: "running",
  done_bytes: 504_000_000,
  total_bytes: 1_260_000_000,
  error: null,
  code: null,
  detail: null,
  terms_url: null,
  started_at: "2026-10-29T10:00:00Z",
  finished_at: null,
  ...over,
});

test("a language is said with its article and in a sentence", () => {
  assert.equal(theLanguage("Anglais"), "l'anglais");
  assert.equal(theLanguage("Français"), "le français");
  assert.equal(inLanguage([french, language({})], "en"), "En anglais");
  // A language the engine no longer offers: said so, never French.
  assert.equal(inLanguage([french], "nl"), "Langue plus prise en charge");
});

test("a version without a language in its provenance is unknown, never French", () => {
  assert.equal(versionLanguage([french], "fr"), "français");
  assert.equal(versionLanguage([french], null), "langue inconnue");
});

test("a language says where it stands: installed, downloading, failed, to download", () => {
  assert.equal(languageNote(french), "installé");
  assert.equal(languageNote(language({})), "à télécharger · 1,3 Go");
  assert.equal(
    languageNote(language({ downloads: [action({})] })),
    "téléchargement : 40 %",
  );
  assert.deepEqual(
    languageState(
      language({
        downloads: [action({ state: "failed", error: "Réseau coupé." })],
      }),
    ),
    {
      kind: "failed",
      error: "Réseau coupé.",
    },
  );
});

test("one bar for a language, whatever the number of its models", () => {
  const two = language({
    download_bytes: 2_000_000_000,
    downloads: [
      action({ done_bytes: 500_000_000, total_bytes: 1_000_000_000 }),
    ],
  });
  // The model not started yet counts in the total.
  assert.deepEqual(languageState(two), {
    kind: "downloading",
    done: 500_000_000,
    total: 2_000_000_000,
  });
});

test("the shared transcription downloading: no language says it downloads, but a waiting session does", () => {
  const english = language({
    missing_models: ["asr", "wav2vec2-ctc-english"],
    downloads: [action({ name: "asr", done_bytes: 1_000_000_000, total_bytes: 2_470_000_000 })],
  });
  assert.equal(languageState(english).kind, "missing");
  assert.equal(languageNote(english), "à télécharger · 1,3 Go");
  assert.equal(languageCards([french, english]).cards.length, 1);
  // A session waiting in English waits on it too.
  assert.deepEqual(languageState(english, true), { kind: "downloading", done: 1_000_000_000, total: 2_470_000_000 });
  // Its own model downloading: it does; with the shared one lacking too, its own size
  // (from the catalog) makes the bar's total.
  const own = language({ missing_models: ["asr", "wav2vec2-ctc-english"], downloads: [action({ done_bytes: 100, total_bytes: null })] });
  assert.deepEqual(languageState(own, false, 1_260_000_000), { kind: "downloading", done: 100, total: 1_260_000_000 });
  // The shared one failing is the « Transcription » line's to say, not each language's.
  const failedShared = language({ missing_models: ["asr", "wav2vec2-ctc-english"], downloads: [action({ name: "asr", state: "failed", error: "Réseau coupé." })] });
  assert.equal(languageState(failedShared).kind, "missing");
  assert.equal(languageState(failedShared, true).kind, "failed");
});

test("all in French, the language is not shown above the title", () => {
  assert.equal(languageWorthShowing([french, language({})], "fr"), false);
  assert.equal(
    languageWorthShowing([french, language({ installed: true })], "fr"),
    true,
  );
  assert.equal(
    languageWorthShowing([french, language({ downloads: [action({})] })], "fr"),
    true,
  );
  assert.equal(languageWorthShowing([french], "en"), true);
});

test("a language in use says where, with a link to each", () => {
  const used = language({
    used_by: {
      spaces: [{ id: 3, name: "Réunions", archived: false }],
      waiting_sessions: [
        {
          id: "20261029-101500-ab12",
          title: null,
          recorded_at: "2026-10-29T09:15:00Z",
        },
      ],
    },
  });
  assert.deepEqual(
    languageUses(used).map((u) => [u.name, u.href]),
    [
      ["Réunions", "#/espaces/3"],
      ["Séance du jeudi 29 octobre 2026", "#/seance/20261029-101500-ab12"],
    ],
  );
  assert.deepEqual(languageUses(language({})), []);
});

test("a waiting processing says what it waits for", () => {
  const wait: ProcessingWait = {
    reason: "model_missing",
    language: "en",
    label: "Anglais",
    missing_models: ["wav2vec2-ctc-english"],
    download_bytes: 1_260_000_000,
  };
  assert.equal(
    waitWords(wait, language({})).title,
    "Le modèle anglais n'est pas sur ce Mac",
  );
  const coming = waitWords(wait, language({ downloads: [action({})] }));
  assert.equal(coming.title, "En attente du modèle anglais");
  assert.deepEqual(coming.downloading, {
    done: 504_000_000,
    total: 1_260_000_000,
  });
  assert.equal(
    waitWords(
      {
        ...wait,
        reason: "language_unsupported",
        label: null,
        download_bytes: 0,
      },
      undefined,
    ).title,
    "La langue de cette séance n'est plus prise en charge",
  );
});

test("a version in a language no longer offered says so; a failed download shows nothing new", () => {
  assert.equal(versionLanguage([french], "nl"), "langue plus prise en charge");
  assert.equal(
    languageWorthShowing([french, language({ downloads: [action({ state: "failed", error: "Réseau coupé." })] })], "fr"),
    false,
  );
});

test("French is included: never removed, whatever its models", () => {
  assert.equal(
    canRemoveLanguage({ ...french, own_models: ["wav2vec2-ctc-french"] }),
    false,
  );
  assert.equal(canRemoveLanguage(language({ installed: true })), true);
  assert.equal(canRemoveLanguage(language({})), false);
});

test("a rerun of a version without a language waits for it to be chosen", () => {
  assert.equal(rerunLanguageMissing("transcribe", "fr", null), false);
  assert.equal(rerunLanguageMissing("transcribe", null, null), true);
  assert.equal(rerunLanguageMissing("all", null, "en"), false);
  // The voices alone keep the text, and with it its language: nothing to choose.
  assert.equal(rerunLanguageMissing("diarize", null, null), false);
});

test("a language's size: its own models only, unknown when one is not announced", () => {
  const catalog = [{ key: "wav2vec2-ctc-english", announced_bytes: 1_260_000_000 }];
  assert.equal(languageSize(language({}), catalog), 1_260_000_000);
  assert.equal(languageSize(language({}), []), null);
  assert.equal(languageSize(french, catalog), null);
});

test("Réglages: French and what is on this Mac in cards, the rest to add once French is there", () => {
  const english = language({ installed: true });
  const spanish = language({ language: "es", label: "Espagnol" });
  const german = language({
    language: "de",
    label: "Allemand",
    used_by: { spaces: [{ id: 2, name: "Berlin", archived: false }], waiting_sessions: [] },
  });
  const { cards, toAdd } = languageCards([french, english, spanish, german]);
  // A language a space has by default is a card, even not downloaded: its space is named.
  assert.deepEqual(cards.map((l) => l.language), ["fr", "en", "de"]);
  assert.deepEqual(toAdd.map((l) => l.language), ["es"]);
  const fresh = languageCards([{ ...french, installed: false }, spanish]);
  assert.deepEqual(fresh.toAdd, []);
});

test("« Supprimer » only where no space has the language by default", () => {
  assert.equal(offersRemoval(language({ installed: true })), true);
  assert.equal(
    offersRemoval(language({ installed: true, used_by: { spaces: [{ id: 1, name: "Réunions", archived: true }], waiting_sessions: [] } })),
    false,
  );
  assert.equal(offersRemoval(french), false);
});
