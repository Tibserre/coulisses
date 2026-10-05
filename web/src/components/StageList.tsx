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

/** Every stage of the chain, with its state, progress and error (P8). Computing time,
 *  memory and provenance (P7) are shown in developer mode. */
export function StageList({
  stages,
  onShowProvenance,
}: {
  stages: StageView[];
  onShowProvenance: (stage: StageView) => void;
}) {
  const dev = useDevMode();
  return (
    <ol className="cl-stages">
      {stages.map((s) => (
        <li key={s.stage} className="cl-stages__item" data-state={s.state}>
          <StatusDot variant={DOT[s.state]} label={STATE_TEXT[s.state]} isPulsing={s.state === "running"} />
          <div className="cl-stages__body">
            <div className="cl-stages__head">
              <Text weight="medium">{s.label}</Text>
              <Text type="supporting">
                {STATE_TEXT[s.state]}
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
            {s.error && (
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
