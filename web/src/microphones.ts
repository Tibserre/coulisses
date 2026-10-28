/** The microphones while recording (ADR 0067), kept apart to be tested: the main one and
 *  those added, what the bar says of them, which can still be added, and what the timeline
 *  shows of their cuts. The computer's sound is not one of them: it keeps its own button. */
import type { Cut, InputDevice, RecordingState, TrackState } from "./api.ts";

export interface Mic {
  sourceId: string;
  device: string;
  muted: boolean;
  /** It stopped, or nothing arrives from it any more. */
  lost: boolean;
  rms_db: number;
  peak_db: number;
  clipping: boolean;
  cuts: Cut[];
  /** When it was first heard, measured on the main microphone: 0 from the start. */
  startedAt: number;
  /** When it was taken away, measured; null while it records. */
  removedAt: number | null;
}

type MicsOf = Pick<
  RecordingState,
  | "source_id"
  | "device"
  | "muted"
  | "levels"
  | "cuts"
  | "too_quiet"
  | "error"
  | "clipping"
  | "extra"
  | "removed"
>;

/** The main microphone first, then those added, in the order they came. */
export function microphones(state: MicsOf): Mic[] {
  return [
    {
      sourceId: state.source_id,
      device: state.device,
      muted: state.muted,
      lost: state.error !== null,
      rms_db: state.levels.rms_db,
      peak_db: state.levels.peak_db,
      clipping: state.clipping,
      cuts: state.cuts,
      startedAt: 0,
      removedAt: null,
    },
    ...state.extra.map(track),
  ];
}

/** Every microphone of the recording, those taken away too: what the timeline tells. */
export function timelineMics(state: MicsOf): Mic[] {
  return [...microphones(state), ...state.removed.map(track)];
}

function track(t: TrackState): Mic {
  return {
    sourceId: t.source_id,
    device: t.device,
    muted: t.muted,
    lost: t.error !== null || (!t.muted && t.too_quiet),
    rms_db: t.levels.rms_db,
    peak_db: t.levels.peak_db,
    clipping: t.clipping,
    cuts: t.cuts,
    startedAt: t.started_at_s,
    removedAt: t.removed_at_s,
  };
}

/** What the bar says beside the microphone: how many, how many cut, all of them cut. */
export function micSummary(mics: readonly Mic[]): {
  count: number;
  cut: number;
  allCut: boolean;
  lost: boolean;
} {
  const cut = mics.filter((m) => m.muted).length;
  return {
    count: mics.length,
    cut,
    allCut: mics.length > 0 && cut === mics.length,
    lost: mics.some((m) => m.lost),
  };
}

/** The level the bar shows: the loudest microphone not cut, so that one can see sound
 *  arrives; none when they are all cut. */
export function barLevel(mics: readonly Mic[]): {
  rms_db: number;
  peak_db: number;
} {
  const open = mics.filter((m) => !m.muted);
  if (!open.length) return { rms_db: -120, peak_db: -120 };
  return {
    rms_db: Math.max(...open.map((m) => m.rms_db)),
    peak_db: Math.max(...open.map((m) => m.peak_db)),
  };
}

/** The microphones one can still add: those the Mac has, not already recording. */
export function addable(
  devices: readonly InputDevice[],
  mics: readonly Mic[],
): InputDevice[] {
  const taken = new Set(mics.map((m) => m.device));
  return devices.filter((d) => !taken.has(d.name));
}

/** A phone, by its name: drawn as one. */
export function isPhone(device: string): boolean {
  return /iphone|ipad/i.test(device);
}

export interface MicEvent {
  key: string;
  at: number;
  text: string;
}

/** What the timeline says of the microphones, at their measured times: each one added,
 *  each taken away, each cut and each return. A cut that leaves them all cut is said once.
 *  `mics`: all of them, those taken away too (`timelineMics`). */
export function micEvents(mics: readonly Mic[]): MicEvent[] {
  const events: MicEvent[] = [];
  for (const m of mics) {
    if (m.startedAt > 0)
      events.push({
        key: `added-${m.sourceId}`,
        at: m.startedAt,
        text: `${m.device} ajouté`,
      });
    if (m.removedAt !== null)
      events.push({
        key: `removed-${m.sourceId}`,
        at: m.removedAt,
        text: `${m.device} retiré · enregistrement gardé`,
      });
  }
  // Cuts and returns, grouped by their time.
  const groups = new Map<
    string,
    { at: number; back: boolean; names: string[] }
  >();
  for (const m of mics)
    for (const c of m.cuts) {
      const moments: [number, boolean][] = [[c.from_s, false]];
      // A cut closed by taking the microphone away is no return.
      if (c.to_s !== null && c.to_s !== m.removedAt)
        moments.push([c.to_s, true]);
      for (const [at, back] of moments) {
        const key = `${back ? "back" : "cut"}-${at.toFixed(1)}`;
        const g = groups.get(key) ?? { at, back, names: [] };
        g.names.push(m.device);
        groups.set(key, g);
      }
    }
  for (const [key, g] of groups) {
    // Those recording then (one added later, or taken away before, is not counted) and
    // those cut just after: a cut that leaves them all cut, or a return that brings them
    // all back, is « the microphones ».
    const present = mics.filter(
      (m) =>
        m.startedAt <= g.at && (m.removedAt === null || m.removedAt > g.at),
    );
    const cutAfter = present.filter((m) =>
      m.cuts.some(
        (c) =>
          c.from_s <= g.at + 0.05 && (c.to_s === null || c.to_s > g.at + 0.05),
      ),
    );
    const whole = g.back
      ? cutAfter.length === 0 && g.names.length > 1
      : cutAfter.length === present.length && present.length > 1;
    const several = g.names.length > 1;
    events.push({
      key,
      at: g.at,
      text: whole
        ? g.back
          ? "Micros rétablis"
          : "Micros coupés"
        : `${list(g.names)} ${g.back ? "rétabli" : "coupé"}${several ? "s" : ""}`,
    });
  }
  return events.sort((a, b) => a.at - b.at);
}

function list(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} et ${names[names.length - 1]}`;
}
