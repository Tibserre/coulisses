import { useEffect, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { api, ServiceError, type Session } from "../api.ts";
import { libraryChanged } from "../library.ts";
import { leaveMessage } from "../retention.ts";

export type Asking = "audio" | "session" | "replace" | "stop" | null;

/** The session's own options (spec §7.10): keep its audio, delete its audio, delete it
 *  entirely (its processing stopped first, ADR 0070), stop its processing. Each is
 *  confirmed, saying what is lost for good. */
export function SessionMenu({
  session,
  onChanged,
  onError,
  onIncomplete,
  onDone,
  onVersions,
  onRerun,
  request,
  onRequestRead,
  hasTranscript = false,
}: {
  session: Session;
  /** Its corrected transcript can be read: it can be downloaded. */
  hasTranscript?: boolean;
  /** A confirmation asked from elsewhere on the page (« Arrêter le traitement »,
   *  « Supprimer la séance… » under a stopped processing): the same windows. */
  request?: Asking;
  onRequestRead?: () => void;
  /** Opens « Refaire le traitement ». */
  onRerun?: () => void;
  /** Opens « Versions » (ADR 0062, 0066). */
  onVersions?: () => void;
  onChanged: (session: Session) => void;
  onError: (message: string) => void;
  /** Done in Coulisses, but something stayed on the disk. */
  onIncomplete: (message: string) => void;
  /** Done, said in passing (an export written). */
  onDone?: (message: string) => void;
}) {
  const [asking, setAsking] = useState<Asking>(null);
  const [working, setWorking] = useState(false);
  useEffect(() => {
    if (!request) return;
    setAsking(request);
    onRequestRead?.();
  }, [request, onRequestRead]);
  const processing =
    session.job_state === "queued" || session.job_state === "running";
  const removed = session.audio.state === "removed";
  const kept = session.audio.state === "kept";

  const [existing, setExisting] = useState<string | null>(null);
  const exportNow = async (replace: boolean) => {
    try {
      const { fichier, resume } = await api.exportToFolder(
        session.id,
        "tout",
        null,
        replace,
      );
      setAsking(null);
      onDone?.(
        resume
          ? `Exporté dans le dossier : ${fichier} (« ${resume} » et la transcription).`
          : `Exporté dans le dossier : ${fichier} (la transcription seule : aucun résumé n'est fait).`,
      );
    } catch (e) {
      if (e instanceof ServiceError && e.status === 409) {
        setExisting(e.message);
        setAsking("replace");
      } else {
        setAsking(null);
        onError((e as Error).message);
      }
    }
  };

  const run = (action: () => Promise<void>) => async () => {
    setWorking(true);
    try {
      await action();
      setAsking(null);
    } catch (e) {
      setAsking(null);
      onError((e as Error).message);
    } finally {
      setWorking(false);
    }
  };

  return (
    <>
      <MoreMenu
        label="Options de la séance"
        alignment="end"
        items={[
          ...(removed
            ? []
            : [
                {
                  // Short: the rule (kept from the purge, or purged after a notice) is said in
                  // the Réglages; a purge always comes with a notice first (ADR 0029).
                  label: kept ? "Ne plus garder l'audio" : "Garder l'audio",
                  onClick: () =>
                    void run(async () =>
                      onChanged(await api.keepAudio(session.id, !kept)),
                    )(),
                },
                {
                  label: "Supprimer l'audio…",
                  onClick: () => setAsking("audio"),
                },
              ]),
          ...(hasTranscript
            ? [
                {
                  // The browser (or the Dock app's save window) takes the attachment.
                  label: "Télécharger la transcription (.md)",
                  onClick: () =>
                    void run(async () => {
                      const url = api.exportUrl(session.id, "transcript");
                      await api.checkExport(url);
                      window.location.href = url;
                    })(),
                },
              ]
            : []),
          {
            label: "Exporter vers le dossier",
            onClick: () => void exportNow(false),
          },
          ...(onRerun && !removed
            ? [{ label: "Refaire le traitement…", onClick: onRerun }]
            : []),
          ...(onVersions ? [{ label: "Versions…", onClick: onVersions }] : []),
          ...(processing
            ? [{ label: "Arrêter le traitement…", onClick: () => setAsking("stop") }]
            : []),
          { type: "divider" as const },
          {
            label: "Supprimer la séance…",
            variant: "destructive" as const,
            onClick: () => setAsking("session"),
          },
        ]}
      />
      <AlertDialog
        isOpen={asking === "audio"}
        onOpenChange={(open) => !open && setAsking(null)}
        title="Supprimer l'audio ?"
        description="Le fichier audio est supprimé définitivement. La transcription, les noms, les corrections, les notes et les résumés restent ; on ne pourra plus réécouter la séance ni refaire la transcription ou la séparation des voix."
        actionLabel="Supprimer l'audio"
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={run(async () => {
          const { session: next, problems } = await api.removeAudio(session.id);
          onChanged(next);
          if (problems.length)
            onIncomplete(
              `L'audio est supprimé de Coulisses, mais pas entièrement du disque : ${problems.join(" ; ")}.`,
            );
        })}
      />
      <AlertDialog
        isOpen={asking === "session"}
        onOpenChange={(open) => !open && setAsking(null)}
        title="Supprimer la séance ?"
        description={`${processing ? "Son traitement est arrêté d'abord. " : ""}Tout est supprimé définitivement : l'audio, la transcription, vos corrections, les notes, les chapitres et les résumés, y compris dans les sauvegardes de la base. Seule une trace reste dans le journal des suppressions : la date et la taille des fichiers, sans aucun texte.`}
        actionLabel="Supprimer la séance"
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={run(async () => {
          const { problems } = await api.deleteSession(session.id);
          libraryChanged();
          if (problems.length)
            leaveMessage(
              `La séance est supprimée de Coulisses, mais pas entièrement du disque : ${problems.join(" ; ")}.`,
            );
          window.location.hash = "#/";
        })}
      />
      <AlertDialog
        isOpen={asking === "stop"}
        onOpenChange={(open) => !open && setAsking(null)}
        title="Arrêter le traitement ?"
        description="La transcription et la séparation des voix s'arrêtent. Ce qui est déjà fait est gardé : « Reprendre » relancera le reste. Rien n'est supprimé."
        actionLabel="Arrêter le traitement"
        cancelLabel="Continuer"
        isActionLoading={working}
        onAction={run(async () => {
          const next = await api.stopProcessing(session.id);
          onChanged(next);
          if (next.job_state === "running")
            onDone?.(
              "Arrêt en cours : il se fera à la fin de l'étape en cours.",
            );
        })}
      />
      <AlertDialog
        isOpen={asking === "replace"}
        onOpenChange={(open) => !open && setAsking(null)}
        title="Remplacer le fichier ?"
        description={`${existing ?? ""} L'export le remplacera ; si vous l'aviez modifié à la main, ces modifications seront perdues.`}
        actionLabel="Remplacer"
        cancelLabel="Annuler"
        onAction={() => void exportNow(true)}
      />
    </>
  );
}
