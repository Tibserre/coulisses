/**
 * Speaker palette and font fallbacks of the Coulisses theme.
 * Rationale and rules: docs/produit/direction-artistique.md.
 */
import type { TokenValue } from "@astryxdesign/core/theme";

export const SANS_FALLBACKS =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

/** Speaker palette: [light ink, light tint, dark ink, dark tint]. Hues stay
 *  away from the warm accents so selection and identity never blur. */
const SPEAKER_COLORS: ReadonlyArray<readonly [string, string, string, string]> =
  [
    ["#a33d78", "#ffe6f3", "#f79dcb", "#3f2432"], // framboise
    ["#0075ae", "#d8f3ff", "#61cbfd", "#133240"], // ciel
    ["#697100", "#eef2d7", "#bdc668", "#2d3014"], // olive
    ["#824ba9", "#f5e9ff", "#d4a8f8", "#34273f"], // prune
    ["#00817f", "#d5f6f4", "#46d6d1", "#0b3534"], // sarcelle
    ["#995700", "#fdecd5", "#ebb25f", "#3b2a12"], // ambre
    ["#4860be", "#e5eeff", "#a0baff", "#252d45"], // bleuet
    ["#00803b", "#def6e4", "#7dd499", "#1b3423"], // menthe
  ];

export const SPEAKER_COLOR_COUNT = SPEAKER_COLORS.length;

/** CSS variable holding the ink (name, rail, initials) of speaker slot `i`. */
export function speakerInk(i: number): string {
  return `var(--coulisses-speaker-${(i % SPEAKER_COLOR_COUNT) + 1}-ink)`;
}

/** CSS variable holding the background tint of speaker slot `i`. */
export function speakerTint(i: number): string {
  return `var(--coulisses-speaker-${(i % SPEAKER_COLOR_COUNT) + 1}-tint)`;
}

/** Theme tokens for the speaker palette: one ink and one tint per slot. */
export function speakerTokens(): Record<string, TokenValue> {
  const tokens: Record<string, TokenValue> = {};
  SPEAKER_COLORS.forEach(([inkLight, tintLight, inkDark, tintDark], i) => {
    tokens[`--coulisses-speaker-${i + 1}-ink`] = [inkLight, inkDark];
    tokens[`--coulisses-speaker-${i + 1}-tint`] = [tintLight, tintDark];
  });
  return tokens;
}
