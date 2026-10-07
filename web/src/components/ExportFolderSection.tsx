import { useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { api, type ExportFolder } from "../api.ts";

/** The export folder (Q7, ADR 0030): chosen once with the Finder's own window, often a
 *  folder that Google Drive keeps in sync. Coulisses only writes files there. */
export function ExportFolderSection() {
  const [folder, setFolder] = useState<ExportFolder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [choosing, setChoosing] = useState(false);
  useEffect(() => {
    api.exportFolder().then(setFolder, (e: Error) => setError(e.message));
  }, []);
  const choose = async () => {
    setChoosing(true);
    try {
      setFolder(await api.chooseExportFolder());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChoosing(false);
    }
  };
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Dossier d'export</Heading>
      <Text color="secondary">
        « Exporter vers le dossier », dans le menu « … » d'une séance, y dépose son compte rendu
        en Markdown. Choisissez par exemple un dossier synchronisé par Google Drive : il le
        mettra en ligne de lui-même. Coulisses n'envoie rien sur Internet.
      </Text>
      {folder?.folder ? (
        <Text>
          <span className="cl-path">{folder.folder}</span>
          {!folder.present && " : introuvable pour l'instant (disque débranché, Google Drive déconnecté ?)"}
        </Text>
      ) : (
        <Text type="supporting">Aucun dossier choisi.</Text>
      )}
      <div className="cl-settings__buttons">
        <Button
          size="sm"
          label={choosing ? "Choix dans le Finder…" : folder?.folder ? "Changer de dossier" : "Choisir un dossier"}
          isDisabled={choosing}
          clickAction={choose}
        />
        {folder?.folder && (
          <Button
            size="sm"
            variant="ghost"
            label="Ne plus exporter vers un dossier"
            clickAction={async () => {
              try {
                setFolder(await api.setExportFolder(null));
                setError(null);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          />
        )}
      </div>
      {error && <Banner status="error" title="Refusé" description={error} />}
    </section>
  );
}
