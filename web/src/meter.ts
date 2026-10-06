/** The meter's range, in dBFS: below, silence; 0, full scale. */
const FLOOR_DB = -60;

/** 0 to 100 from a level in dBFS, as the meter and the drawing show it. */
export function meterValue(db: number): number {
  return Math.round(Math.max(0, Math.min(1, (db - FLOOR_DB) / -FLOOR_DB)) * 100);
}
