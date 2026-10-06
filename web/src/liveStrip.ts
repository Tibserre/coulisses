/**
 * The chapters as they are being marked while recording: from each play or discussion
 * marker to the next, the stretch before the first one left without a mode (the
 * detection fills it afterwards). Times are recorded times: measured, never estimated.
 */
import type { Marker } from "./api.ts";

export type Mode = "scene" | "discussion";

export interface LiveSegment {
  /** None: before the first marker, left to the detection. */
  kind: Mode | "none";
  start: number;
  end: number;
}

/** The mode in force: that of the last play or discussion marker, if any. */
export function currentMode(markers: readonly Marker[]): { mode: Mode; since: number } | null {
  const last = [...markers]
    .filter((m) => m.kind !== "key_moment")
    .sort((a, b) => a.at_s - b.at_s || a.id - b.id)
    .at(-1);
  return last ? { mode: last.kind as Mode, since: last.at_s } : null;
}

export function liveSegments(markers: readonly Marker[], elapsed: number): LiveSegment[] {
  const cuts = markers
    .filter((m) => m.kind !== "key_moment")
    .sort((a, b) => a.at_s - b.at_s || a.id - b.id);
  const segments: LiveSegment[] = [];
  let start = 0;
  let kind: LiveSegment["kind"] = "none";
  for (const cut of cuts) {
    if (cut.at_s > start) segments.push({ kind, start, end: cut.at_s });
    start = Math.max(start, cut.at_s);
    kind = cut.kind as Mode;
  }
  if (elapsed > start || segments.length === 0) segments.push({ kind, start, end: Math.max(start, elapsed) });
  return segments;
}

/** At most this far ahead of the last time the service gave, the strip moves on by itself
 *  between two updates (display only: recorded times stay measured, P2). */
export const AHEAD_MAX_S = 0.25;

/** The time the strip shows at a frame: the time given, carried on for at most
 *  `AHEAD_MAX_S` while recording, never going back; exactly the time given when paused
 *  or with reduced motion. */
export function shownElapsed(
  given: number,
  sinceGiven_s: number,
  lastShown: number,
  still: boolean,
): number {
  if (still) return given;
  const ahead = given + Math.min(AHEAD_MAX_S, Math.max(0, sinceGiven_s));
  return Math.max(Math.min(lastShown, given + AHEAD_MAX_S), ahead);
}
