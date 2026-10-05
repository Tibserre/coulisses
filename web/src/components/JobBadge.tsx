import { Badge } from "@astryxdesign/core/Badge";
import type { JobState } from "../api.ts";

const LABELS: Record<JobState, { label: string; variant: "neutral" | "info" | "success" | "error" }> = {
  queued: { label: "En file", variant: "neutral" },
  running: { label: "En traitement", variant: "info" },
  done: { label: "Prête", variant: "success" },
  failed: { label: "En erreur", variant: "error" },
};

export function JobBadge({ state }: { state: JobState | null }) {
  if (state === null) return <Badge variant="neutral" label="Jamais traitée" />;
  const { label, variant } = LABELS[state];
  return <Badge variant={variant} label={label} />;
}
