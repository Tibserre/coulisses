import { useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { api, type Provenance, type StageView } from "../api.ts";
import { formatBytes, formatDateTime, formatDuration } from "../format.ts";

/** Who produced a result, with what, how long it took (P7). */
export function ProvenanceDialog({
  sessionId,
  stage,
  onClose,
}: {
  sessionId: string;
  stage: StageView | null;
  onClose: () => void;
}) {
  const [prov, setProv] = useState<Provenance | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setProv(null);
    setError(null);
    if (!stage?.run_id) return;
    api.provenance(sessionId, stage.run_id).then(setProv, (e: Error) => setError(e.message));
  }, [sessionId, stage]);

  return (
    <Dialog isOpen={stage !== null} onOpenChange={(open) => !open && onClose()} width={620}>
      <DialogHeader title={`Provenance : ${stage?.label ?? ""}`} subtitle={stage?.run_id} onOpenChange={() => onClose()} />
      <div className="cl-dialog-body">
        {error && <Banner status="error" title="Provenance illisible" description={error} />}
        {!prov && !error && <Spinner label="Lecture de la provenance" />}
        {prov && (
          <MetadataList label={{ position: "start", width: 170 }}>
            <MetadataListItem label="État">{prov.status === "succeeded" ? "Réussie" : "En échec"}</MetadataListItem>
            {prov.error && (
              <MetadataListItem label="Erreur">
                {prov.error.type} : {prov.error.message}
              </MetadataListItem>
            )}
            <MetadataListItem label="Moteur">{prov.engine_id}</MetadataListItem>
            <MetadataListItem label="Version du moteur">{prov.coulisses_version}</MetadataListItem>
            <MetadataListItem label="Modèle">
              {prov.model ? `${prov.model.repo} @ ${prov.model.revision.slice(0, 12)}` : "aucun"}
            </MetadataListItem>
            <MetadataListItem label="Réglages">
              <code className="cl-code">{JSON.stringify(prov.settings)}</code>
            </MetadataListItem>
            <MetadataListItem label="Bibliothèques">
              <Text type="supporting">
                {Object.entries(prov.versions)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(" · ") || "—"}
              </Text>
            </MetadataListItem>
            <MetadataListItem label="Début">{formatDateTime(prov.started_at)}</MetadataListItem>
            <MetadataListItem label="Durée">{formatDuration(prov.duration_s)}</MetadataListItem>
            <MetadataListItem label="Mémoire au plus">
              {prov.max_rss_bytes ? formatBytes(prov.max_rss_bytes) : "inconnue"}
            </MetadataListItem>
            <MetadataListItem label="Machine">
              {Object.values(prov.machine).join(" · ")}
            </MetadataListItem>
          </MetadataList>
        )}
      </div>
    </Dialog>
  );
}
