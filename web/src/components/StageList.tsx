import { Button } from "@astryxdesign/core/Button";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import type { StageView } from "../api.ts";
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

function unitText(unit: "s" | "windows" | "steps", done: number, total: number): string {
  if (unit === "s") return `${formatDuration(done)} sur ${formatDuration(total)} d'audio`;
  return `${Math.round(done)} sur ${Math.round(total)}`;
}

/** Every stage of the chain, with its state, progress, error and provenance (P7, P8). */
export function StageList({
  stages,
  onShowProvenance,
}: {
  stages: StageView[];
  onShowProvenance: (stage: StageView) => void;
}) {
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
                {s.duration_s != null && ` · ${formatDuration(s.duration_s)} de calcul`}
                {s.max_rss_bytes != null && ` · ${formatBytes(s.max_rss_bytes)} de mémoire au plus`}
              </Text>
            </div>
            {s.state === "running" &&
              (s.progress ? (
                <ProgressBar
                  label={`${s.label} : ${s.progress.phase}`}
                  value={s.progress.total > 0 ? (100 * s.progress.done) / s.progress.total : 0}
                  hasValueLabel
                  formatValueLabel={() =>
                    `${s.progress!.phase} · ${unitText(s.progress!.unit, s.progress!.done, s.progress!.total)}`
                  }
                />
              ) : (
                <ProgressBar label={s.label} isIndeterminate />
              ))}
            {s.error && <Text as="p" color="primary" type="supporting">{s.error}</Text>}
            {s.folder_missing && (
              <Text as="p" type="supporting">
                Le dossier de cette étape est introuvable : a-t-il été supprimé dans le Finder ?
              </Text>
            )}
            {(s.state === "succeeded" || s.state === "failed") && s.run_id && !s.folder_missing && (
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
