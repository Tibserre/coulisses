// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import type { RecordingState, TrackState } from "./api.ts";
import {
  addable,
  timelineMics,
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
  started_at_s: 0,
  removed_at_s: null,
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
    removed: [],
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

test("the timeline says what was added, each cut and return", () => {
  const mics = microphones(
    state({ cuts: [{ from_s: 300, to_s: null }] }, [
      track("mic2", "iPhone", {
        cuts: [
          { from_s: 120, to_s: 180 },
          { from_s: 300, to_s: null },
        ],
      }),
      track("mic3", "Micro USB", {
        started_at_s: 200,
        cuts: [{ from_s: 300, to_s: null }],
      }),
    ]),
  );
  const events = micEvents(mics);
  assert.deepEqual(
    events.map((e) => [e.at, e.text]),
    [
      [120, "iPhone coupé"],
      [180, "iPhone rétabli"],
      [200, "Micro USB ajouté"],
      [300, "Micros coupés"],
    ],
  );
});

test("a cut that leaves them all cut is « the microphones », one added later aside", () => {
  const mics = microphones(
    state({ cuts: [{ from_s: 250, to_s: 400 }] }, [
      track("mic2", "iPhone", { cuts: [{ from_s: 100, to_s: null }] }),
      track("mic3", "Micro USB", {
        started_at_s: 200,
        cuts: [{ from_s: 250, to_s: 400 }],
      }),
    ]),
  );
  const said = micEvents(mics).map((e) => e.text);
  assert.deepEqual(said, [
    "iPhone coupé",
    "Micro USB ajouté",
    "Micros coupés",
    "Micro du MacBook et Micro USB rétablis",
  ]);
});

test("one taken away is told, and not counted after it went", () => {
  const mics = timelineMics({
    ...state({ cuts: [{ from_s: 500, to_s: null }] }),
    removed: [
      track("mic2", "iPhone", {
        started_at_s: 120,
        removed_at_s: 130,
        cuts: [{ from_s: 125, to_s: 130 }],
      }),
    ],
  } as RecordingState);
  assert.deepEqual(
    micEvents(mics).map((e) => [e.at, e.text]),
    [
      [120, "iPhone ajouté"],
      [125, "iPhone coupé"],
      [130, "iPhone retiré · enregistrement gardé"],
      [500, "Micro du MacBook coupé"],
    ],
  );
});
