import { Button } from "@astryxdesign/core/Button";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import type { StageView } from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { describeStageError } from "../errors.ts";
import { formatBytes, formatDuration } from "../format.ts";

const STATE_TEXT: Record<StageView["state"], string> = {
  pending: "À venir",
  running: "En cours",
  stalled: "Silencieuse depuis 15 min : probablement arrêtée",
  succeeded: "Terminée",
  failed: "En échec",
};

/** Of the version shown, made again by a rerun: kept, and shown until the new one is complete. */
const STALE_TEXT = "Périmée : refaite par la relance";

const DOT: Record<StageView["state"], "neutral" | "accent" | "warning" | "success" | "error"> = {
  pending: "neutral",
  running: "accent",
  stalled: "warning",
  succeeded: "success",
  failed: "error",
};

function progressText(p: NonNullable<StageView["progress"]>, dev: boolean): string {
  const percent = p.total > 0 ? Math.round((100 * p.done) / p.total) : 0;
  if (!dev) return `${percent} %`;
  const amount =
    p.unit === "s"
      ? `${formatDuration(p.done)} sur ${formatDuration(p.total)} d'audio`
      : `${Math.round(p.done)} sur ${Math.round(p.total)}`;
  return `${p.phase} · ${amount}`;
}

/** A stage the service says was stopped (ADR 0070): by the user's stop, or interrupted
 *  (the app closed, or after a crash). */
const STOPPED_TEXT = "Arrêtée à votre demande";
const INTERRUPTED_TEXT = "Interrompue";

/** Every stage of the chain, with its state, progress and error (P8). Computing time,
 *  memory and provenance (P7) are shown in developer mode. */
export function StageList({
  stages,
  onShowProvenance,
  stoppedByUser = false,
}: {
  stages: StageView[];
  onShowProvenance: (stage: StageView) => void;
  /** The session's processing was stopped by the user: its stopped stages say so. */
  stoppedByUser?: boolean;
}) {
  const haltedText = stoppedByUser ? STOPPED_TEXT : INTERRUPTED_TEXT;
  const dev = useDevMode();
  // Cancelled by a stop the user asked (the service says so, stage by stage): said as
  // stopped, its error in developer mode. A real failure, even of an earlier try, stays one.
  const halted = (s: StageView) => s.state === "failed" && s.stopped;
  return (
    <ol className="cl-stages">
      {stages.map((s) => (
        <li key={s.stage} className="cl-stages__item" data-state={s.state} data-stale={s.stale || undefined}>
          <StatusDot
            variant={s.stale || halted(s) ? "neutral" : DOT[s.state]}
            label={s.stale ? STALE_TEXT : halted(s) ? haltedText : STATE_TEXT[s.state]}
            isPulsing={s.state === "running"}
          />
          <div className="cl-stages__body">
            <div className="cl-stages__head">
              <Text weight="medium">{s.label}</Text>
              <Text type="supporting">
                {s.stale ? STALE_TEXT : halted(s) ? haltedText : STATE_TEXT[s.state]}
                {dev && s.duration_s != null && ` · ${formatDuration(s.duration_s)} de calcul`}
                {dev &&
                  s.max_rss_bytes != null &&
                  ` · ${formatBytes(s.max_rss_bytes)} de mémoire au plus`}
              </Text>
            </div>
            {s.state === "running" &&
              (s.progress ? (
                <ProgressBar
                  label={dev ? `${s.label} : ${s.progress.phase}` : s.label}
                  value={s.progress.total > 0 ? (100 * s.progress.done) / s.progress.total : 0}
                  hasValueLabel
                  formatValueLabel={() => progressText(s.progress!, dev)}
                />
              ) : (
                <ProgressBar label={s.label} isIndeterminate />
              ))}
            {s.error && (!halted(s) || dev) && (
              <Text as="p" color="primary" type="supporting">
                {dev ? s.error : describeStageError(s)}
              </Text>
            )}
            {s.folder_missing && (
              <Text as="p" type="supporting">
                Le dossier de cette étape est introuvable : a-t-il été supprimé dans le Finder ?
              </Text>
            )}
            {dev && (s.state === "succeeded" || s.state === "failed") && s.run_id && !s.folder_missing && (
              <div>
                <Button label="Provenance" variant="ghost" size="sm" onClick={() => onShowProvenance(s)} />
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
