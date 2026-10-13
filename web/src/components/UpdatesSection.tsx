import { useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import { appUpdates } from "../appBridge.ts";
import { formatDateTime } from "../format.ts";

/** Settings, « Données »: the published app's updates (ADR 0040, spec §7.12). Sparkle in
 *  the app looks for them, after consent or on demand; nothing installs without a click.
 *  Not shown where there are none (development app, browser). */
export function UpdatesSection() {
  const [updates] = useState(() => appUpdates());
  const [automatic, setAutomatic] = useState(updates?.state.automatic ?? false);
  if (updates === null) return null;
  const last = updates.state.lastCheck;
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Mises à jour</Heading>
      <Text color="secondary">
        Coulisses peut chercher sa nouvelle version sur GitHub. Avec le
        téléchargement des modèles et de leurs environnements, c'est la seule
        fois où elle utilise internet, et elle n'envoie rien d'autre que cette
        demande. Une nouvelle version ne se télécharge et ne s'installe que
        quand vous le choisissez, jamais pendant un enregistrement ou un
        traitement.
      </Text>
      <Switch
        label="Chercher automatiquement, une fois par jour"
        value={automatic}
        onChange={(on) => {
          setAutomatic(on);
          updates.setAutomatic(on);
        }}
      />
      <div className="cl-settings__buttons">
        <Button
          label="Chercher maintenant"
          size="sm"
          onClick={updates.checkNow}
        />
      </div>
      <Text type="supporting">
        {last
          ? `Dernière recherche : ${formatDateTime(last)}.`
          : "Aucune recherche pour l'instant."}
      </Text>
    </section>
  );
}
