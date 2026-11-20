/**
 * The recording's wave (D5a): one bar for each fifth of a second of recorded time, its
 * height the loudest level heard in it (measured by the service, never estimated: a stretch
 * with no level heard has no bar). Twenty pixels a second (some 38 s in sight), the present
 * `nowX` pixels from the left.
 */
import { meterValue } from "./meter.ts";

export const WAVE = {
  pxPerSecond: 20,
  secondsPerBar: 0.2,
  /** The present, from the left of the wave's box. */
  nowX: 760,
  midY: 92,
  /** Half the tallest bar. */
  maxHalf: 52,
  /** Around a key moment, the bars are marked: from a little before to a little after. */
  markBefore: 1,
  markAfter: 4,
} as const;

export interface WaveBar {
  x: number;
  /** 0 to 1. */
  height: number;
  marked: boolean;
}

/** The bars in sight at `shown` seconds, from the loudest level (dBFS) heard in each. */
export function waveBars(
  levels: ReadonlyMap<number, number>,
  shown: number,
  moments: readonly number[],
): WaveBar[] {
  const { pxPerSecond: px, secondsPerBar: spb, nowX } = WAVE;
  const first = Math.max(0, Math.floor((shown - nowX / px) / spb));
  const last = Math.floor(shown / spb);
  const bars: WaveBar[] = [];
  for (let i = first; i <= last; i++) {
    const db = levels.get(i);
    if (db === undefined) continue;
    const x = nowX - (shown - i * spb) * px + 1;
    if (x < 0 || x > nowX) continue;
    const t = (i + 0.5) * spb;
    bars.push({
      x,
      height: meterValue(db) / 100,
      marked: moments.some((m) => t >= m - WAVE.markBefore && t <= m + WAVE.markAfter),
    });
  }
  return bars;
}

/** The four live bars, oldest first, from the last four levels received (dBFS): none yet,
 *  the lowest height (nothing made up). */
export function liveHeights(recent: readonly number[]): number[] {
  return [0, 1, 2, 3].map((k) => {
    const db = recent[recent.length - 4 + k];
    return Math.max(3, ((db === undefined ? 0 : meterValue(db)) / 100) * 2 * WAVE.maxHalf);
  });
}
