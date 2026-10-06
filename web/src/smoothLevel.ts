/**
 * The level as a meter's needle shows it: quick to rise, slow to fall, at the screen's own
 * pace (the service sends it ten times a second; drawn as is, it jumps). Pure: one step
 * per frame, from the time elapsed since the last one.
 */

/** Seconds for the shown level to cover about two thirds of the way up or down. */
export const ATTACK_S = 0.05;
export const RELEASE_S = 0.35;
/** A peak stays this long, then falls at `PEAK_FALL_PER_S` (0–100 per second). */
export const PEAK_HOLD_S = 0.8;
export const PEAK_FALL_PER_S = 60;

export interface Needle {
  level: number;
  peak: number;
  /** Time the peak has been held. */
  held: number;
}

export function step(
  needle: Needle,
  target: number,
  peakTarget: number,
  dt: number,
): Needle {
  const tau = target > needle.level ? ATTACK_S : RELEASE_S;
  const level =
    needle.level + (target - needle.level) * (1 - Math.exp(-dt / tau));
  if (peakTarget >= needle.peak) return { level, peak: peakTarget, held: 0 };
  const held = needle.held + dt;
  const peak =
    held < PEAK_HOLD_S
      ? needle.peak
      : Math.max(peakTarget, needle.peak - PEAK_FALL_PER_S * dt);
  return { level, peak: Math.max(peak, level), held };
}
