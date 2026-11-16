import { useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Text } from "@astryxdesign/core/Text";
import { Folder } from "lucide-react";
import { api, type ExportFolder } from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { folderName } from "../settingsParts.ts";

/** The export folder (Q7, ADR 0030): chosen once with the Finder's own window, often a
 *  folder that Google Drive keeps in sync. Coulisses only writes files there. A card: the
 *  folder by its name (its path in developer mode), and what changes it. */
export function ExportFolderSection() {
  const dev = useDevMode();
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
  const chosen = folder?.folder ?? null;
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Comptes rendus</Heading>
      <div className="cl-folder-card">
        <span className="cl-icon-disc">
          <Folder size={18} strokeWidth={1.75} aria-hidden />
        </span>
        <span className="cl-settings__text">
          {folder === null && !error ? (
            <Skeleton width={160} height={14} radius={1} />
          ) : chosen ? (
            <Text weight="medium">
              {dev ? (
                <span className="cl-path">{chosen}</span>
              ) : (
                folderName(chosen)
              )}
              {!folder?.present && " (introuvable pour l'instant)"}
            </Text>
          ) : (
            <Text weight="medium">Aucun dossier d'export</Text>
          )}
          <Text type="supporting">
            « Exporter vers le dossier », dans le menu « … » d'une séance, y
            dépose son compte rendu.
          </Text>
        </span>
        <span className="cl-settings__value">
          {chosen && (
            <Button
              size="sm"
              variant="ghost"
              label="Retirer"
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
          <Button
            size="sm"
            label={
              choosing
                ? "Choix dans le Finder…"
                : chosen
                  ? "Changer"
                  : "Choisir"
            }
            isDisabled={choosing || (folder === null && !error)}
            clickAction={choose}
          />
        </span>
      </div>
      {chosen && !folder?.present && (
        <Text type="supporting">
          Disque débranché, ou Google Drive déconnecté ? Rebranchez-le avant
          d'exporter.
        </Text>
      )}
      {error && <Banner status="error" title="Refusé" description={error} />}
    </section>
  );
}
