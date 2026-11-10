// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { CatalogModel, Language, MissingPiece, ModelAction, ModelsView } from "./api.ts";
import { appSystemAudio } from "./appBridge.ts";
import {
  basePieces,
  languageChoices,
  lineRunning,
  lineStarted,
  lineState,
  linesRunning,
  linesToResume,
  toResume,
  onboardingDownload,
  progressLines,
  sizeWords,
} from "./onboarding.ts";

const model = (key: string, stage: CatalogModel["stage"], bytes: number): CatalogModel => ({
  key,
  stage,
  role: stage,
  description: "",
  announced_bytes: bytes,
  repo: "r",
  revision: "v",
  licence: "l",
  terms_url: null,
  engine: null,
  required_by: ["chaine-retenue"],
  replaced_by: null,
  replacement_note: null,
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

const CATALOG = [
  model("asr", "transcribe", 2_470_000_000),
  model("align-fr", "align", 1_260_000_000),
  model("align-en", "align", 1_260_000_000),
  model("voix-a", "diarize", 280_000_000),
  model("voix-b", "diarize", 60_000_000),
];

const fresh = (missing: MissingPiece[] = [
  lacking({ model: "asr" }),
  lacking({ model: "align-fr", stage: "align" }),
  lacking({ model: "voix-a", stage: "diarize" }),
  lacking({ model: "voix-b", stage: "diarize" }),
  lacking({ code: "environment_missing", stage: "diarize", environment: "diarizen" }),
]): ModelsView => ({
  catalog: { models: CATALOG },
  inventory: { models_dir: "", envs_dir: "", models: [], partial_downloads: [], environments: [], uv_stores: [], total_bytes: 0 },
  readiness: { profile: "chaine-retenue", ready: false, missing },
  actions: [],
});

const english: Language = {
  language: "en",
  label: "Anglais",
  installed: false,
  missing_models: ["asr", "align-en"],
  download_bytes: 3_730_000_000,
  models: ["asr", "align-en"],
  own_models: ["align-en"],
  downloads: [],
  used_by: { spaces: [], waiting_sessions: [] },
};
const french: Language = { ...english, language: "fr", label: "Français", own_models: ["align-fr"], missing_models: ["asr", "align-fr"] };

const action = (name: string, over: Partial<ModelAction> = {}): ModelAction => ({
  kind: "model",
  name,
  state: "running",
  done_bytes: 0,
  total_bytes: null,
  error: null,
  code: null,
  detail: null,
  terms_url: null,
  started_at: "2026-11-10T10:00:00Z",
  finished_at: null,
  ...over,
});

const LABELS = { transcribe: "Transcription", align: "Alignement des mots", diarize: "Qui parle quand", tools: "Outils de calcul" };

test("one tile per thing it is for, in the order of the processing; an environment's size unknown", () => {
  const pieces = basePieces(fresh());
  assert.deepEqual(pieces.map((p) => [p.kind, p.bytes]), [
    ["transcribe", 2_470_000_000],
    ["align", 1_260_000_000],
    ["diarize", 340_000_000],
    ["tools", null],
  ]);
  assert.equal(sizeWords(null, () => "x"), "selon ce Mac");
});

test("engine v1.15.0 sizes an environment: the tools say « environ », the total too", () => {
  const sized = fresh([
    lacking({ model: "asr" }),
    lacking({ code: "environment_missing", stage: "diarize", environment: "diarizen", announced_bytes: 900_000_000 }),
  ]);
  const pieces = basePieces(sized);
  const tools = pieces.find((p) => p.kind === "tools")!;
  assert.equal(tools.bytes, 900_000_000);
  assert.equal(tools.approximate, true);
  assert.equal(sizeWords(tools.bytes, () => "0,9 Go", tools.approximate), "environ 0,9 Go");
  const all = onboardingDownload(pieces, []);
  assert.equal(all.bytes, 3_370_000_000);
  assert.equal(all.more, false);
  assert.equal(all.approximate, true);
});

test("a language adds only its own models; French is not offered, it is included", () => {
  const choices = languageChoices([french, english], CATALOG);
  assert.deepEqual(choices.map((c) => [c.language.language, c.models, c.bytes]), [["en", ["align-en"], 1_260_000_000]]);
});

test("the one total: the pieces plus the chosen languages, « au moins » with the tools", () => {
  const pieces = basePieces(fresh());
  const all = onboardingDownload(pieces, languageChoices([english], CATALOG));
  assert.deepEqual(all.download, ["asr", "align-fr", "voix-a", "voix-b", "align-en"]);
  assert.deepEqual(all.install, ["diarizen"]);
  assert.equal(all.bytes, 5_330_000_000);
  assert.equal(all.more, true);
});

test("the progress: one line per piece, one per chosen language after French", () => {
  const lines = progressLines(basePieces(fresh()), languageChoices([english], CATALOG), LABELS);
  assert.deepEqual(lines.map((l) => l.label), [
    "Transcription",
    "Alignement, français",
    "Alignement, anglais",
    "Qui parle quand",
    "Outils de calcul",
  ]);
});

test("a line: waiting, running with its share, done once the engine no longer lacks it, failed said", () => {
  const view = fresh();
  const [transcribe] = progressLines(basePieces(view), [], LABELS);
  assert.deepEqual(lineState(transcribe, view, []), { kind: "waiting" });
  assert.deepEqual(lineState(transcribe, view, [action("asr", { done_bytes: 1, total_bytes: 4 })]), { kind: "running", percent: 25 });
  assert.deepEqual(
    lineState(transcribe, view, [action("asr", { state: "failed", error: "Réseau coupé." })]),
    { kind: "failed", error: "Réseau coupé." },
  );
  const after = fresh([lacking({ model: "align-fr", stage: "align" })]);
  assert.deepEqual(lineState(transcribe, after, []), { kind: "done" });
  const [, , en] = progressLines(basePieces(view), languageChoices([english], CATALOG), LABELS);
  assert.deepEqual(lineState(en, view, [action("align-en", { state: "done" })]), { kind: "done" });
});

test("the computer's sound: read from the app, never guessed", () => {
  assert.equal(appSystemAudio({}), null);
  assert.equal(appSystemAudio({ coulissesApp: { systemAudio: "denied" } }), "denied");
  assert.equal(appSystemAudio({ coulissesApp: { systemAudio: "maybe" } }), null);
});

test("a line stopped (here or from the settings) says so, until it is over", () => {
  const view = fresh();
  const [transcribe] = progressLines(basePieces(view), [], LABELS);
  assert.deepEqual(lineState(transcribe, view, [action("asr", { state: "cancelled" })]), { kind: "stopped" });
  const after = fresh([lacking({ model: "align-fr", stage: "align" })]);
  assert.deepEqual(lineState(transcribe, after, [action("asr", { state: "cancelled" })]), { kind: "done" });
});

test("a line half failed, half running: stop what runs, resume only what failed", () => {
  const view = fresh();
  const [, , diarize] = progressLines(basePieces(view), [], LABELS);
  const acts = [action("voix-a", { state: "failed", error: "Réseau coupé." }), action("voix-b")];
  assert.equal(lineState(diarize, view, acts).kind, "failed");
  assert.equal(lineRunning(diarize, acts), true);
  assert.deepEqual(toResume(diarize, view, acts), { models: ["voix-a"], environments: [] });
  // One done, one stopped: only the stopped one again.
  assert.deepEqual(
    toResume(diarize, view, [action("voix-a", { state: "done" }), action("voix-b", { state: "cancelled" })]),
    { models: ["voix-b"], environments: [] },
  );
});

test("a line already started (even failed or stopped) is followed, not offered again", () => {
  const view = fresh();
  const [transcribe] = progressLines(basePieces(view), [], LABELS);
  assert.equal(lineStarted(transcribe, []), false);
  assert.equal(lineStarted(transcribe, [action("asr", { state: "failed" })]), true);
  assert.equal(lineStarted(transcribe, [action("voix-a")]), false);
});

test("one control for every piece: all that runs stops together, all that waits resumes together", () => {
  const view = fresh();
  const lines = progressLines(basePieces(view), [], LABELS);
  const actions = [
    action("asr"),
    action("align-fr", { state: "failed", error: "Réseau coupé." }),
    action("voix-a", { state: "cancelled" }),
    action("autre-chose"),
  ];
  // What runs for these lines only: another download (a language added) is not stopped.
  assert.deepEqual(linesRunning(lines, actions).map((a) => a.name), ["asr"]);
  // What resumes: the failed, the stopped, what never started (a refused start), once each.
  const left = linesToResume(lines, view, actions);
  assert.ok(left.models.includes("align-fr") && left.models.includes("voix-a") && left.models.includes("voix-b"));
  assert.ok(!left.models.includes("asr"));
  assert.equal(new Set(left.models).size, left.models.length);
  assert.deepEqual(left.environments, ["diarizen"]);
});
