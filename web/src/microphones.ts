/** The microphones while recording (ADR 0067), kept apart to be tested: the main one and
 *  those added, what the bar says of them, which can still be added, and what the timeline
 *  shows of their cuts. The computer's sound is not one of them: it keeps its own button. */
import type { Cut, InputDevice, LastTime, RecordingState } from "./api.ts";

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
    },
    ...state.extra.map((t) => ({
      sourceId: t.source_id,
      device: t.device,
      muted: t.muted,
      lost: t.error !== null || (!t.muted && t.too_quiet),
      rms_db: t.levels.rms_db,
      peak_db: t.levels.peak_db,
      clipping: t.clipping,
      cuts: t.cuts,
    })),
  ];
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

/** What the timeline says of the microphones: last time's taken or missing at the start,
 *  each one added (when this page saw it come), each cut and each return. A cut of every
 *  microphone at once is said once. */
export function micEvents(
  mics: readonly Mic[],
  lastTime: LastTime | null,
  addedAt: ReadonlyMap<string, number>,
): MicEvent[] {
  const events: MicEvent[] = [];
  if (lastTime?.taken.length)
    events.push({
      key: "last-taken",
      at: 0,
      text: `Avec ${list([mics[0]?.device ?? "le micro", ...lastTime.taken])}, comme la dernière fois`,
    });
  for (const name of lastTime?.missing ?? [])
    events.push({
      key: `last-missing-${name}`,
      at: 0,
      text: `${name} n'est pas là : démarré sans lui`,
    });
  for (const m of mics) {
    const at = addedAt.get(m.sourceId);
    if (at !== undefined)
      events.push({
        key: `added-${m.sourceId}`,
        at,
        text: `${m.device} ajouté`,
      });
  }
  // Cuts, grouped by time: every microphone at the same time is « the microphones ».
  const groups = new Map<
    string,
    { at: number; back: boolean; names: string[] }
  >();
  for (const m of mics)
    for (const c of m.cuts) {
      const moments: [number, boolean][] = [[c.from_s, false]];
      if (c.to_s !== null) moments.push([c.to_s, true]);
      for (const [at, back] of moments) {
        const key = `${back ? "back" : "cut"}-${at.toFixed(1)}`;
        const g = groups.get(key) ?? { at, back, names: [] };
        g.names.push(m.device);
        groups.set(key, g);
      }
    }
  for (const [key, g] of groups) {
    // Those recording then (one added later is not counted) and those cut just after: when
    // a cut leaves them all cut, or a return brings them all back, it is « the
    // microphones ».
    const present = mics.filter((m) => (addedAt.get(m.sourceId) ?? 0) <= g.at);
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
