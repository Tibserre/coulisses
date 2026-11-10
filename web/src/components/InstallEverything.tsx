import { useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import {
  downloadEverything,
  everythingSize,
  type Everything,
} from "../steps.ts";

/** « Tout télécharger » (spec §7.12): everything the processing lacks, in one click, always
 *  asked first (P1). Refused: said in the window itself, which stays open (P8). */
export function InstallEverything({
  everything,
  after,
  variant = "primary",
  onStarted,
  onRefused,
}: {
  everything: Everything;
  /** What happens once it is there, in a sentence (« La séance sera traitée juste après. »). */
  after?: string;
  variant?: "primary" | "secondary";
  /** Read again what shows the progress. */
  onStarted: () => void;
  /** A refusal, said also by whoever shows this button: the button may be gone once what
   *  started changes what is shown (P8). */
  onRefused?: (message: string) => void;
}) {
  const [asking, setAsking] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const size = everythingSize(everything);
  const start = async () => {
    setWorking(true);
    setError(null);
    try {
      await downloadEverything(everything);
      setAsking(false);
    } catch (e) {
      const said = (e as Error).message;
      setError(said);
      onRefused?.(`Le téléchargement n'a pas démarré en entier : ${said}`);
    } finally {
      setWorking(false);
      onStarted();
    }
  };
  return (
    <>
      <Button
        label={
          everything.more ? "Tout télécharger" : `Tout télécharger (${size})`
        }
        variant={variant}
        onClick={() => setAsking(true)}
      />
      <AlertDialog
        isOpen={asking}
        onOpenChange={(open) => {
          if (open) return;
          setAsking(false);
          setError(null);
        }}
        title="Télécharger de quoi écouter vos séances ?"
        description={`${size.charAt(0).toUpperCase()}${size.slice(1)} depuis internet, une seule fois ; ensuite, tout reste sur ce Mac. Vous pouvez l'arrêter : il reprendra là où il s'est arrêté.${after ? ` ${after}` : ""}${error ? ` Le téléchargement n'a pas démarré en entier : ${error}` : ""}`}
        actionLabel="Tout télécharger"
        actionVariant="primary"
        cancelLabel="Plus tard"
        isActionLoading={working}
        onAction={() => void start()}
      />
    </>
  );
}
