import { useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import { appUpdates } from "../appBridge.ts";
import { formatDateTime } from "../format.ts";

/** Settings, « Ce Mac »: the published app's updates (ADR 0040, spec §7.12). Sparkle in the
 *  app looks for them, after consent or on demand; nothing installs without a click. The
 *  version is a quiet line (ADR 0051), said in the development app and the browser too, which
 *  look for none. */
export function UpdatesSection({ version }: { version: string | null }) {
  const [updates] = useState(() => appUpdates());
  const [automatic, setAutomatic] = useState(updates?.state.automatic ?? false);
  const last = updates?.state.lastCheck ?? null;
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Mises à jour</Heading>
      {updates === null ? (
        <Text color="secondary">Cette app ne cherche pas de mises à jour.</Text>
      ) : (
        <>
          <Text color="secondary">
            Coulisses peut chercher sa nouvelle version sur GitHub, sans rien
            envoyer d'autre que cette demande. Elle ne s'installe que quand vous
            le choisissez, jamais pendant un enregistrement ou un traitement.
          </Text>
          <Switch
            label="Chercher automatiquement, une fois par jour"
            value={automatic}
            onChange={(on) => {
              setAutomatic(on);
              updates.setAutomatic(on);
            }}
          />
          <div className="cl-settings__line">
            <Text type="supporting">
              {last
                ? `Dernière recherche : ${formatDateTime(last)}.`
                : "Aucune recherche pour l'instant."}
            </Text>
            <Button
              label="Chercher maintenant"
              size="sm"
              onClick={updates.checkNow}
            />
          </div>
        </>
      )}
      {/* Its place kept while the service answers: nothing moves. */}
      <Text type="supporting">{version ? `Version ${version}` : " "}</Text>
    </section>
  );
}
