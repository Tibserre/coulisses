import { useEffect, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Heading } from "@astryxdesign/core/Heading";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Text } from "@astryxdesign/core/Text";
import { Check } from "lucide-react";
import { api, type Language, type ModelsView } from "../api.ts";
import { lastModelsView, onStepsChanged } from "../steps.ts";
import { gigabytes } from "../models.ts";
import {
  FRENCH,
  languageCards,
  offersRemoval,
  downloadPercent,
  languageSize,
  languageState,
  languageUses,
  languageWord,
  theLanguage,
} from "../languages.ts";
import { LanguageDownloadDialog, useLanguages } from "./Languages.tsx";

/** « Langues », in Réglages › Transcription (ADR 0072, 0079): a compact card per language on
 *  this Mac, with its size and the spaces that have it by default; the others to add, one
 *  at a time. Removed only while nothing needs it. Its models are said here, not among the
 *  models (outside developer mode). */
export function LanguagesSection({
  onError,
}: {
  onError: (message: string | null) => void;
}) {
  const { languages, reload } = useLanguages(onError);
  const [adding, setAdding] = useState<Language | null>(null);
  const [removing, setRemoving] = useState<Language | null>(null);
  /** « Ajouter une langue »: the languages to add, as tiles; one chosen, then confirmed. */
  const [picking, setPicking] = useState(false);
  const [working, setWorking] = useState(false);
  const act = async (what: () => Promise<unknown>) => {
    setWorking(true);
    try {
      await what();
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setWorking(false);
      await reload();
    }
  };
  const uses = removing ? languageUses(removing) : [];
  // The catalog's sizes: each language said with its own models' size (ADR 0079).
  const [view, setView] = useState<ModelsView | null>(lastModelsView);
  useEffect(() => onStepsChanged(setView), []);
  const catalog = view?.catalog.models ?? [];
  const { cards: shown, toAdd } = languageCards(languages ?? []);
  const french = languages?.find((l) => l.language === FRENCH);
  const capital = (text: string) =>
    `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Langues</Heading>
      {languages === null ? (
        <Skeleton width={320} height={14} radius={1} />
      ) : (
        <>
          <div className="cl-langcards">
            {shown.map((l) => {
              const size = languageSize(l, catalog);
              const state = languageState(l, false, size);
              const spaces = l.used_by.spaces;
              return (
                <div key={l.language} className="cl-langcard">
                  <div className="cl-langcard__line">
                    <Text weight="medium">{l.label}</Text>
                    <Text type="supporting">
                      {l.language === FRENCH
                        ? "Inclus"
                        : size === null
                          ? ""
                          : gigabytes(size)}
                    </Text>
                  </div>
                  {state.kind === "downloading" ? (
                    <div className="cl-langcard__progress">
                      <ProgressBar
                        label={`Téléchargement de ${theLanguage(l.label)}`}
                        value={downloadPercent(state.done, state.total)}
                        hasValueLabel
                      />
                    </div>
                  ) : (
                    <div className="cl-langcard__spaces">
                      {spaces.length > 0 ? (
                        spaces.map((space) => (
                          <a
                            key={space.id}
                            className="cl-langcard__space"
                            href={`#/espaces/${space.id}`}
                            title="Langue par défaut de cet espace"
                          >
                            <Check size={10} strokeWidth={2.5} aria-hidden />
                            {space.archived ? `${space.name} (archivé)` : space.name}
                          </a>
                        ))
                      ) : (
                        <Text type="supporting">Aucun espace</Text>
                      )}
                      {offersRemoval(l) && (
                        <button
                          type="button"
                          className="cl-linkbtn cl-langcard__act"
                          disabled={working}
                          onClick={() => setRemoving(l)}
                        >
                          Supprimer
                        </button>
                      )}
                    </div>
                  )}
                  {state.kind === "failed" && (
                    <>
                      <Text type="supporting" color="primary">
                        {state.error}
                      </Text>
                      <button
                        type="button"
                        className="cl-linkbtn cl-langcard__act"
                        disabled={working}
                        onClick={() => setAdding(l)}
                      >
                        Réessayer
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
          {french && !french.installed && (
            <Text type="supporting">
              Les autres langues s'ajoutent une fois ce qui manque téléchargé,
              plus bas.
            </Text>
          )}
          {toAdd.length > 0 && (
            <div>
              <Button
                label="+ Ajouter une langue"
                size="sm"
                isDisabled={working}
                onClick={() => setPicking(true)}
              />
            </div>
          )}
        </>
      )}

      <Dialog
        isOpen={picking}
        onOpenChange={(open) => !open && setPicking(false)}
        width={560}
        aria-label="Ajouter une langue"
      >
        <div className="cl-onb">
          <h2 className="cl-onb__title">Ajouter une langue</h2>
          <p className="cl-onb__text">
            Pour les séances dans cette langue. Une à la fois ; le français est
            inclus.
          </p>
          <div className="cl-onb__langs">
            {toAdd.map((l) => (
              <button
                key={l.language}
                type="button"
                className="cl-onb__lang"
                onClick={() => {
                  setPicking(false);
                  setAdding(l);
                }}
              >
                <span className="cl-onb__name">{l.label}</span>
                <span className="cl-onb__what">
                  {l.download_bytes ? gigabytes(l.download_bytes) : ""}
                </span>
              </button>
            ))}
          </div>
          <div className="cl-onb__actions cl-onb__actions--end">
            <Button
              label="Annuler"
              variant="ghost"
              onClick={() => setPicking(false)}
            />
          </div>
        </div>
      </Dialog>
      <LanguageDownloadDialog
        language={adding}
        onClose={() => setAdding(null)}
        onStarted={() => void reload()}
      />
      {/* Needed still: said where, with the way there, before anything is asked of the
          service (which refuses it too, 409). */}
      <Dialog
        isOpen={removing !== null && uses.length > 0}
        onOpenChange={(open) => !open && setRemoving(null)}
        width={480}
      >
        <DialogHeader
          title={
            removing
              ? `${capital(theLanguage(removing.label))} sert encore`
              : ""
          }
          onOpenChange={() => setRemoving(null)}
        />
        <div className="cl-languageuses">
          <Text as="p" color="secondary">
            Coulisses ne peut pas la supprimer tant que des séances en ont
            besoin. Changez d'abord leur langue :
          </Text>
          <ul className="cl-languageuses__list">
            {uses.map((u) => (
              <li key={u.key}>
                <span className="cl-languageuses__what">
                  <Text>{u.name}</Text>
                  <Text type="supporting">{u.why}</Text>
                </span>
                <a href={u.href} onClick={() => setRemoving(null)}>
                  {u.key.startsWith("space-")
                    ? "Paramètres de l'espace"
                    : "Ouvrir la séance"}
                </a>
              </li>
            ))}
          </ul>
          <Text as="p" type="supporting">
            Les séances déjà transcrites dans cette langue n'en ont plus besoin
            : elles restent lisibles.
          </Text>
          <div className="cl-languageuses__actions">
            <Button
              variant="primary"
              label="Compris"
              onClick={() => setRemoving(null)}
            />
          </div>
        </div>
      </Dialog>
      <AlertDialog
        isOpen={removing !== null && uses.length === 0}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={removing ? `Supprimer ${theLanguage(removing.label)} ?` : ""}
        description={
          removing
            ? `Le modèle propre à ${theLanguage(removing.label)} est retiré de ce Mac ; le modèle de transcription, commun à toutes les langues, reste. Les séances déjà transcrites en ${languageWord(removing.label)} restent lisibles, avec leurs corrections. Pour en traiter une nouvelle, ou refaire leur texte, il faudra le télécharger à nouveau.`
            : ""
        }
        actionLabel={
          removing ? `Supprimer ${theLanguage(removing.label)}` : "Supprimer"
        }
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={() => {
          const language = removing;
          if (!language) return;
          void act(async () => {
            for (const key of language.own_models) await api.removeModel(key);
          }).then(() => setRemoving(null));
        }}
      />
    </section>
  );
}
