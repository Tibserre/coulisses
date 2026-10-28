// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { RecordingState, TrackState } from "./api.ts";
import {
  addable,
  barLevel,
  isPhone,
  micEvents,
  micSummary,
  microphones,
} from "./microphones.ts";

const track = (
  sourceId: string,
  device: string,
  more: Partial<TrackState> = {},
): TrackState => ({
  device,
  source_id: sourceId,
  levels: { rms_db: -30, peak_db: -20 },
  too_quiet: false,
  clipping: false,
  dropouts: 0,
  error: null,
  muted: false,
  cuts: [],
  ...more,
});
const state = (more: Partial<RecordingState> = {}, extra: TrackState[] = []) =>
  ({
    source_id: "ref",
    device: "Micro du MacBook",
    muted: false,
    levels: { rms_db: -40, peak_db: -30 },
    cuts: [],
    too_quiet: false,
    clipping: false,
    error: null,
    extra,
    ...more,
  }) as RecordingState;

test("the main microphone first, then those added; a quiet one cut is not lost", () => {
  const mics = microphones(
    state({}, [
      track("mic2", "iPhone", { too_quiet: true }),
      track("mic3", "Micro USB", { too_quiet: true, muted: true }),
    ]),
  );
  assert.deepEqual(
    mics.map((m) => [m.sourceId, m.lost]),
    [
      ["ref", false],
      ["mic2", true],
      ["mic3", false],
    ],
  );
});

test("the bar counts them, the cut ones, and says when they are all cut", () => {
  const some = microphones(
    state({}, [track("mic2", "iPhone", { muted: true })]),
  );
  assert.deepEqual(micSummary(some), {
    count: 2,
    cut: 1,
    allCut: false,
    lost: false,
  });
  const all = microphones(
    state({ muted: true }, [track("mic2", "iPhone", { muted: true })]),
  );
  assert.equal(micSummary(all).allCut, true);
});

test("the bar's level is the loudest microphone not cut, none when all are", () => {
  const mics = microphones(
    state({}, [
      track("mic2", "iPhone", {
        levels: { rms_db: -10, peak_db: -5 },
        muted: true,
      }),
    ]),
  );
  assert.deepEqual(barLevel(mics), { rms_db: -40, peak_db: -30 });
  assert.deepEqual(barLevel(mics.map((m) => ({ ...m, muted: true }))), {
    rms_db: -120,
    peak_db: -120,
  });
});

test("only the microphones not already recording can be added", () => {
  const mics = microphones(state({}, [track("mic2", "iPhone")]));
  const devices = [
    { index: 0, name: "Micro du MacBook", channels: 1, default: true },
    { index: 1, name: "iPhone", channels: 1, default: false },
    { index: 2, name: "Micro USB", channels: 1, default: false },
  ];
  assert.deepEqual(
    addable(devices, mics).map((d) => d.name),
    ["Micro USB"],
  );
  assert.equal(isPhone("iPhone de la troupe"), true);
  assert.equal(isPhone("Micro USB"), false);
});

test("the timeline says last time, what was added, each cut and return", () => {
  const mics = microphones(
    state({ cuts: [{ from_s: 300, to_s: null }] }, [
      track("mic2", "iPhone", {
        cuts: [
          { from_s: 120, to_s: 180 },
          { from_s: 300, to_s: null },
        ],
      }),
      track("mic3", "Micro USB", { cuts: [{ from_s: 300, to_s: null }] }),
    ]),
  );
  const events = micEvents(
    mics,
    { taken: ["iPhone"], missing: ["Casque"] },
    new Map([["mic3", 200]]),
  );
  assert.deepEqual(
    events.map((e) => [e.at, e.text]),
    [
      [0, "Avec Micro du MacBook et iPhone, comme la dernière fois"],
      [0, "Casque n'est pas là : démarré sans lui"],
      [120, "iPhone coupé"],
      [180, "iPhone rétabli"],
      [200, "Micro USB ajouté"],
      [300, "Micros coupés"],
    ],
  );
});
