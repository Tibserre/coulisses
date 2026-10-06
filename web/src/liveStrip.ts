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
