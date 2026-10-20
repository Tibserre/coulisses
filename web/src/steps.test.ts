// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CatalogModel, EnvironmentInfo, InstalledEngineModel, MissingPiece, ModelsView } from "./api.ts";
import { lastModelsView, pendingNotices, settleReplacements, stepsChanged, updateNotices } from "./steps.ts";

const model = (key: string, over: Partial<CatalogModel> = {}): CatalogModel => ({
  key,
  stage: "transcribe",
  role: "transcription",
  description: "",
  announced_bytes: 2_470_000_000,
  repo: "r",
  revision: "v",
  licence: "l",
  terms_url: null,
  engine: null,
  required_by: ["chaine-retenue"],
  replaced_by: null,
  replacement_note: null,
  ...over,
});

const there = (key: string, over: Partial<InstalledEngineModel> = {}): InstalledEngineModel => ({
  key,
  state: "intact",
  in_catalog: true,
  repo: null,
  revision: null,
  outdated: false,
  size_bytes: 4_700_000_000,
  downloaded_at: null,
  problem: null,
  required: true,
  replaced_by: null,
  ...over,
});

const env = (name: string, over: Partial<EnvironmentInfo> = {}): EnvironmentInfo => ({
  name,
  path: `/E/${name}-abc`,
  current: true,
  installed: true,
  size_bytes: 1_300_000_000,
  interpreter: null,
  interpreter_outside: false,
  label: "Calcul des modèles",
  stages: [],
  ...over,
});

const lacking = (over: Partial<MissingPiece>): MissingPiece => ({
  code: "model_missing",
  stage: "transcribe",
  model: null,
  environment: null,
  label: null,
  message: "",
  ...over,
});

const view = (
  inventory: Partial<ModelsView["inventory"]>,
  missing: MissingPiece[] = [],
  models: CatalogModel[] = [],
): ModelsView => ({
  catalog: { models },
  inventory: {
    models_dir: "",
    envs_dir: "",
    models: [],
    partial_downloads: [],
    environments: [],
    uv_stores: [],
    total_bytes: 0,
    ...inventory,
  },
  readiness: { profile: "chaine-retenue", ready: missing.length === 0, missing },
  actions: [],
});

const NOTE = "Remplacé par sa version 8 bits, qui fait exactement le même travail.";
const OLD = model("asr-ancien", { required_by: [], replaced_by: "asr", replacement_note: NOTE, announced_bytes: 4_700_000_000 });
const MEASURED = {
  ...OLD,
  replacement_speedup: 1.7,
  replacement_quality: "same" as const,
  replacement_memory_saved_bytes: 1_600_000_000,
  replacement_evidence: "Banc ESLO2",
};

/** A friend after the update to engine v1.10.0: the old model there, the new one lacking,
 *  an environment from an older engine left behind. */
const afterUpdate = view(
  {
    models: [there("asr-ancien", { required: false, replaced_by: "asr" }), there("align")],
    environments: [env("torch"), env("diarizen", { path: "/E/diarizen-vieux", current: false, installed: false })],
  },
  [lacking({ model: "asr" }), lacking({ model: "asr", stage: "align" })],
  [MEASURED, model("asr")],
);

test("after the update: one update at a time, the replacement first, each with two ways out", () => {
  const notices = updateNotices(afterUpdate);
  assert.deepEqual(notices.map((n) => [n.kind, n.choices.map((c) => c.kind)]), [
    ["replacement", ["replace", "later"]],
    ["cleanup", ["removeEnvironments", "keep"]],
  ]);
  const [replacement] = notices;
  assert.equal(replacement.eyebrow, "Mise à jour du moteur de transcription");
  assert.equal(replacement.title, "Une action est attendue de votre part");
  assert.equal(replacement.explanation, "Un nouveau modèle de transcription, plus léger, peut remplacer celui que vous utilisez.");
  assert.deepEqual([replacement.download, replacement.remove], [["asr"], ["asr-ancien"]]);
  // The recommended way out says what it does before it is done: the network, the space.
  assert.equal(replacement.choices[0].recommended, true);
  assert.equal(replacement.choices[0].description, "Télécharge 2,5 Go depuis internet, puis supprime l'ancien (4,7 Go libérés).");
  assert.match(replacement.choices[1].description, /ne pourront pas être traitées/);
});

test("three figures from the engine's measures; its sentence only when it gave none", () => {
  const [replacement] = updateNotices(afterUpdate);
  assert.deepEqual(replacement.gains, [
    { label: "Vitesse", value: "×1,7" },
    { label: "Poids", value: "−2,2 Go" },
    { label: "Qualité", value: "identique" },
  ]);
  assert.equal(replacement.note, null);
  assert.equal(replacement.evidence, "Banc ESLO2");
  // Before engine v1.11.0: the weight from the catalog, and the engine's sentence.
  const [unmeasured] = updateNotices({ ...afterUpdate, catalog: { models: [OLD, model("asr")] } });
  assert.deepEqual(unmeasured.gains, [{ label: "Poids", value: "−2,2 Go" }]);
  // The successor missing from the catalog: still the measures, which are the old one's.
  const [alone] = updateNotices({ ...afterUpdate, catalog: { models: [MEASURED] } });
  assert.deepEqual(alone.gains.map((g) => g.label), ["Vitesse", "Qualité"]);
});

test("a figure that is not a gain is not said as one", () => {
  const slower = { ...MEASURED, replacement_speedup: 0.7, announced_bytes: 1_000_000_000 };
  const [notice] = updateNotices({ ...afterUpdate, catalog: { models: [slower, model("asr")] } });
  assert.deepEqual(notice.gains.slice(0, 2), [
    { label: "Vitesse", value: "plus lente" },
    { label: "Poids", value: "+1,5 Go" },
  ]);
});

test("the new one already there: remove the old one, or keep it for good", () => {
  const v = view(
    { models: [there("asr-ancien", { required: false, replaced_by: "asr" }), there("asr")] },
    [],
    [MEASURED, model("asr")],
  );
  const [notice] = updateNotices(v);
  assert.equal(notice.explanation, "Le nouveau modèle de transcription est installé : l'ancien ne sert plus.");
  assert.deepEqual(notice.choices.map((c) => [c.kind, c.label, c.description]), [
    ["removeOld", "Supprimer l'ancien modèle", "Libère 4,7 Go sur ce Mac."],
    ["keep", "Garder l'ancien modèle", "Il reste sur ce Mac, sans servir."],
  ]);
  // Its own id: keeping the old one for good does not hide a later « Remplacer ».
  assert.equal(notice.id, "ancien:asr-ancien:asr");
});

test("an update keeps its id while it is the same; one kept for good is not asked again", () => {
  const notices = updateNotices(afterUpdate);
  assert.deepEqual(notices.map((n) => n.id), ["remplacement:asr-ancien:asr", "nettoyage:diarizen-vieux"]);
  assert.deepEqual(pendingNotices(notices, ["nettoyage:diarizen-vieux"]).map((n) => n.kind), ["replacement"]);
});

test("what the processing lacks besides is one update to download", () => {
  const v = view({ models: [there("asr")] }, [
    lacking({ model: "voix", stage: "diarize" }),
    lacking({ code: "environment_missing", environment: "torch", label: "Calcul des modèles" }),
    lacking({ code: "environment_missing", stage: "align", environment: "torch" }),
  ], [model("voix", { stage: "diarize", announced_bytes: 300_000_000 })]);
  const [notice] = updateNotices(v);
  assert.equal(notice.eyebrow, "Mise à jour du moteur");
  assert.deepEqual(notice.choices.map((c) => c.label), ["Télécharger", "Plus tard"]);
  // An environment's size is not known before it is installed: never said smaller.
  assert.equal(notice.choices[0].description, "Depuis internet, une seule fois (plus de 300 Mo).");
  assert.deepEqual([notice.download, notice.install], [["voix"], ["torch"]]);
});

test("nothing installed yet: a welcome", () => {
  const [notice] = updateNotices(view({}, [lacking({ model: "asr" })], [model("asr")]));
  assert.equal(notice.eyebrow, "Bienvenue dans Coulisses");
  assert.equal(notice.choices[0].label, "Tout télécharger");
  assert.equal(notice.choices[0].description, "Environ 2,5 Go depuis internet, une seule fois.");
});

test("a damaged model is left to the settings; all done, nothing is asked", () => {
  assert.deepEqual(updateNotices(view({ models: [there("voix", { state: "altered" })] }, [lacking({ code: "model_altered", model: "voix" })])), []);
  assert.deepEqual(updateNotices(view({ models: [there("asr")], environments: [env("torch")] })), []);
});

test("an old environment says what it frees, without its technical name", () => {
  const [, old] = updateNotices(afterUpdate);
  assert.equal(old.explanation, "Une ancienne version d'un composant du moteur est restée sur ce Mac. Elle ne sert plus.");
  assert.equal(old.choices[0].description, "Libère 1,3 Go sur ce Mac.");
});

const action = (state: "running" | "failed" | "cancelled" | "done", started_at = "t2") => ({
  kind: "model" as const,
  name: "asr",
  state,
  started_at,
});

test("a chosen replacement removes the old model only once the new one is installed", () => {
  const pending = [{ id: "r", remove: ["asr-ancien"], when: ["asr"], before: [] }];
  const downloading = view({ models: [there("asr-ancien")] });
  // Still downloading: nothing yet, it waits.
  assert.deepEqual(settleReplacements(pending, downloading, [action("running")]), { ready: [], left: pending });
  // Failed or stopped: dropped, the old one stays.
  assert.deepEqual(settleReplacements(pending, downloading, [action("failed")]), { ready: [], left: [] });
  assert.deepEqual(settleReplacements(pending, downloading, [action("cancelled")]), { ready: [], left: [] });
  // Installed but damaged: not yet.
  const damaged = view({ models: [there("asr-ancien"), there("asr", { state: "altered" })] });
  assert.deepEqual(settleReplacements(pending, damaged, [action("done")]).ready, []);
  // Installed and intact: the old one can go.
  const installed = view({ models: [there("asr-ancien"), there("asr")] });
  assert.deepEqual(settleReplacements(pending, installed, [action("done")]), { ready: pending, left: [] });
});

test("a download that failed before the choice says nothing about this one", () => {
  const pending = [{ id: "r", remove: ["asr-ancien"], when: ["asr"], before: ["t1"] }];
  const downloading = view({ models: [there("asr-ancien")] });
  assert.deepEqual(settleReplacements(pending, downloading, [action("failed", "t1")]).left, pending);
});

test("several replacements settle each on its own", () => {
  const a = { id: "a", remove: ["x-ancien"], when: ["x"], before: [] };
  const b = { id: "b", remove: ["y-ancien"], when: ["y"], before: [] };
  const v = view({ models: [there("x")] });
  assert.deepEqual(settleReplacements([a, b], v, [{ ...action("running"), name: "y" }]), { ready: [a], left: [b] });
});

test("a speed that rounds to the same is said so", () => {
  const same = { ...MEASURED, replacement_speedup: 1.02 };
  const [notice] = updateNotices({ ...afterUpdate, catalog: { models: [same, model("asr")] } });
  assert.deepEqual(notice.gains[0], { label: "Vitesse", value: "aussi rapide" });
});

test("the last reading is kept, for the Transcription tab to open at once", () => {
  (globalThis as { window?: EventTarget }).window ??= new EventTarget();
  assert.equal(lastModelsView(), null);
  const read = { catalog: { models: [] }, actions: [] } as unknown as ModelsView;
  stepsChanged(read);
  assert.equal(lastModelsView(), read);
});
