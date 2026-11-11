import { useEffect, useState } from "react";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { api, type CatalogModel } from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { modelCredits } from "../modelCredits.ts";
import { lastModelsView } from "../steps.ts";

/** The « Crédits » section of the Settings (Avancé, the user's choice): what the models'
 *  licences require the app to say (ADR 0081 of the engine), as the engine's catalog writes
 *  it. A reading that fails is said; nothing to credit (an older engine), no section. */
export function CreditsSection() {
  const dev = useDevMode();
  const [catalog, setCatalog] = useState<CatalogModel[] | null>(
    () => lastModelsView()?.catalog.models ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .engineModels()
      .then((view) => setCatalog(view.catalog.models))
      .catch((e: Error) => setError(e.message));
  }, []);
  const credits = modelCredits(catalog ?? []);
  if (!credits.length && !error) return null;
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Crédits</Heading>
      {credits.length ? (
        <>
          <Text color="secondary">
            Les modèles qui écoutent vos séances sont l'œuvre d'autres
            personnes ; leur licence demande de le dire.
          </Text>
          <div className="cl-credits">
            {credits.map((text) => (
              <Text key={text} type="supporting">
                {text}
              </Text>
            ))}
          </div>
        </>
      ) : (
        <Text color="secondary">
          Les crédits des modèles n'ont pas pu être lus{dev ? ` : ${error}` : "."}
        </Text>
      )}
    </section>
  );
}
