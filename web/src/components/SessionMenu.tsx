import { useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { api, type Session } from "../api.ts";
import { leaveMessage } from "../retention.ts";

type Asking = "audio" | "session" | null;

/** The session's own options (spec §7.10): keep its audio, delete its audio, delete it
 *  entirely. Each deletion is confirmed, saying what is lost for good. */
export function SessionMenu({
  session,
  onChanged,
  onError,
  onIncomplete,
}: {
  session: Session;
  onChanged: (session: Session) => void;
  onError: (message: string) => void;
  /** Done in Coulisses, but something stayed on the disk. */
  onIncomplete: (message: string) => void;
}) {
  const [asking, setAsking] = useState<Asking>(null);
  const [working, setWorking] = useState(false);
  const removed = session.audio.state === "removed";
  const kept = session.audio.state === "kept";

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
                  label: kept ? "Ne plus garder l'audio" : "Garder l'audio",
                  description: kept
                    ? "Il sera supprimé à échéance, après un préavis."
                    : "Il ne sera jamais supprimé automatiquement.",
                  onClick: () => void run(async () => onChanged(await api.keepAudio(session.id, !kept)))(),
                },
                { label: "Supprimer l'audio…", onClick: () => setAsking("audio") },
                { type: "divider" as const },
              ]),
          { label: "Supprimer la séance…", variant: "destructive" as const, onClick: () => setAsking("session") },
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
            onIncomplete(`L'audio est supprimé de Coulisses, mais pas entièrement du disque : ${problems.join(" ; ")}.`);
        })}
      />
      <AlertDialog
        isOpen={asking === "session"}
        onOpenChange={(open) => !open && setAsking(null)}
        title="Supprimer la séance ?"
        description="Tout est supprimé définitivement : l'audio, la transcription, vos corrections, les notes, les chapitres et les résumés, y compris dans les sauvegardes de la base. Seule une trace reste dans le journal des suppressions : la date et la taille des fichiers, sans aucun texte."
        actionLabel="Supprimer la séance"
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={run(async () => {
          const { problems } = await api.deleteSession(session.id);
          if (problems.length)
            leaveMessage(`La séance est supprimée de Coulisses, mais pas entièrement du disque : ${problems.join(" ; ")}.`);
          window.location.hash = "#/";
        })}
      />
    </>
  );
}
