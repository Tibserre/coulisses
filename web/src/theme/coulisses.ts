/**
 * The Coulisses theme: the single art direction retained on 2026-10-02
 * (ADR 0017). Sober and editorial: untinted neutrals, one brick accent,
 * DM Sans headings, Figtree text, sharp corners, no material effects.
 * Rules: docs/produit/direction-artistique.md. Written from the reference
 * explored in the engine's workshop (read, not imported).
 */
import { defineTheme, type TokenValue } from "@astryxdesign/core/theme";
import { neutralIconRegistry } from "@astryxdesign/theme-neutral";
import { SANS_FALLBACKS, speakerTokens } from "./shared.ts";

const ACCENT: [string, string] = ["#a63d1e", "#ec9a78"];

/** Soft, wide, neutral shadows: light that falls rather than a drop outline.
 *  In dark mode a faint light rim replaces most of the shadow. */
const SHADOWS: Record<string, TokenValue> = {
  "--color-shadow": ["#1a1a1a1f", "#00000073"],
  "--shadow-low":
    "0 1px 1px light-dark(#1a1a1a0a, #00000033), " +
    "0 8px 24px -10px light-dark(#1a1a1a29, #00000080), " +
    "inset 0 0 0 1px light-dark(transparent, #ffffff0f)",
  "--shadow-med":
    "0 1px 2px light-dark(#1a1a1a0d, #00000040), " +
    "0 18px 40px -14px light-dark(#1a1a1a33, #00000099), " +
    "inset 0 0 0 1px light-dark(transparent, #ffffff14)",
  "--shadow-high":
    "0 2px 4px light-dark(#1a1a1a12, #0000004d), " +
    "0 32px 64px -20px light-dark(#1a1a1a40, #000000b3), " +
    "inset 0 0 0 1px light-dark(transparent, #ffffff1a)",
};

/** Tactile feedback on pressable controls. */
const PRESS = {
  transitionProperty: "transform, box-shadow, background-color, color",
  transitionDuration: "var(--duration-fast)",
  transitionTimingFunction: "var(--ease-standard)",
  ":hover": { transform: "translateY(-1px)" },
  ":active": { transform: "translateY(0) scale(0.98)" },
} as const;

export const coulissesTheme = defineTheme({
  name: "coulisses",

  color: { accent: ACCENT, neutralStyle: "neutral" },

  typography: {
    scale: { base: 15, ratio: 1.333 },
    body: { family: "Figtree Variable", fallbacks: SANS_FALLBACKS },
    heading: {
      family: "DM Sans Variable",
      fallbacks: SANS_FALLBACKS,
      weight: "medium",
      weights: { 1: "medium", 2: "medium" },
    },
    code: { family: "ui-monospace", fallbacks: '"SF Mono", Menlo, monospace' },
  },

  motion: {
    fast: 160,
    medium: 400,
    slow: 850,
    ratio: 0.75,
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
  },

  tokens: {
    "--color-accent": ACCENT,
    "--color-on-accent": ["#ffffff", "#2a0f06"],

    // Untinted neutrals: no cream, no paper.
    "--color-background-body": ["#fafafa", "#131313"],
    "--color-background-surface": ["#ffffff", "#1b1b1b"],
    "--color-background-card": ["#ffffff", "#181818"],
    "--color-background-popover": ["#ffffff", "#222222"],
    "--color-background-muted": ["#f2f2f2", "#212121"],
    "--color-text-primary": ["#1d1d1f", "#ededed"],
    "--color-text-secondary": ["#6b6b6b", "#a3a3a3"],
    "--color-border": ["#0000001a", "#ffffff17"],

    // Reading size for transcripts: 17px, roomy leading.
    "--text-large-size": "1.0625rem",
    "--text-large-leading": "1.6",

    "--radius-inner": "0.25rem",
    "--radius-element": "0.5rem",
    "--radius-container": "0.625rem",
    "--radius-page": "1rem",

    ...SHADOWS,
    "--focus-outline-color": "var(--color-accent)",
  },

  localTokens: {
    // Review screen.
    "--coulisses-word-current": ["#f5dfd9", "#4a241c"],
    "--coulisses-word-uncertain": ["#a8742f", "#d5a86e"],
    // Chapter weights on timelines: main, side, quiet.
    "--coulisses-chapter-main": ["#f3dcd6", "#472520"],
    "--coulisses-chapter-main-ink": ["#8f3419", "#ec9a78"],
    "--coulisses-chapter-side": ["#e4e4e4", "#2e2e2e"],
    "--coulisses-chapter-side-ink": ["#5c5c5c", "#bdbdbd"],
    "--coulisses-chapter-quiet": ["#efefef", "#262626"],
    "--coulisses-chapter-quiet-ink": ["#8a8a8a", "#8f8f8f"],
    // Unnamed speakers stay grey until someone names them.
    "--coulisses-speaker-unknown-ink": ["#737373", "#a8a8a8"],
    "--coulisses-speaker-unknown-tint": ["#ededed", "#2a2a2a"],
    ...speakerTokens(),
  },

  components: {
    heading: { base: { letterSpacing: "-0.03em" } },
    button: {
      base: {
        borderRadius: "var(--radius-element)",
        fontWeight: "var(--font-weight-medium)",
        ...PRESS,
      },
    },
    "segmented-control": {
      base: { borderRadius: "var(--radius-element)", padding: "var(--spacing-0-5)" },
    },
    "segmented-control-item": { base: { borderRadius: "var(--radius-inner)" } },
    card: { base: { padding: "var(--spacing-4)" } },
    section: { base: { padding: "var(--spacing-4)" } },
  },

  icons: neutralIconRegistry,
});
