import { Badge } from "@astryxdesign/core/Badge";
import type { JobState } from "../api.ts";

const LABELS: Record<JobState, { label: string; variant: "neutral" | "info" | "success" | "error" }> = {
  queued: { label: "En file", variant: "neutral" },
  running: { label: "En traitement", variant: "info" },
  done: { label: "Prête", variant: "success" },
  failed: { label: "En erreur", variant: "error" },
};

export function JobBadge({ state, stopped = false }: { state: JobState | null; stopped?: boolean }) {
  if (state === null) return <Badge variant="neutral" label="Jamais traitée" />;
  // Stopped by the user (ADR 0070): said apart from an error.
  if (state === "failed" && stopped) return <Badge variant="neutral" label="Arrêtée" />;
  const { label, variant } = LABELS[state];
  return <Badge variant={variant} label={label} />;
}
