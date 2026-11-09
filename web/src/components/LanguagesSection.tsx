import { useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Heading } from "@astryxdesign/core/Heading";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Text } from "@astryxdesign/core/Text";
import { api, type Language } from "../api.ts";
import { gigabytes } from "../models.ts";
import {
  canRemoveLanguage,
  downloadPercent,
  languageState,
  languageUses,
  languageWord,
  theLanguage,
} from "../languages.ts";
import { LanguageDownloadDialog, useLanguages } from "./Languages.tsx";

/** « Langues », in Réglages › Transcription (ADR 0072): the languages Coulisses transcribes,
 *  each installed, downloading or to add; removed only while nothing needs it. Its models are
 *  said here, not among the models (outside developer mode). */
export function LanguagesSection({
  onError,
}: {
  onError: (message: string | null) => void;
}) {
  const { languages, reload } = useLanguages(onError);
  const [adding, setAdding] = useState<Language | null>(null);
  const [removing, setRemoving] = useState<Language | null>(null);
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
  const capital = (text: string) =>
    `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
  return (
    <section className="cl-settings__section">
      <Heading level={3}>Langues</Heading>
      <Text color="secondary">
        Les langues dans lesquelles Coulisses sait transcrire. Le français est
        inclus ; chaque autre langue demande un modèle, téléchargé une fois.
      </Text>
      {languages === null ? (
        <Skeleton width={320} height={14} radius={1} />
      ) : (
        <ul className="cl-models">
          {languages.map((l) => {
            const state = languageState(l);
            const spaces = l.used_by.spaces.filter((s) => !s.archived);
            return (
              <li key={l.language} className="cl-models__row">
                <div className="cl-models__what">
                  <Text weight="medium">{l.label}</Text>
                  {spaces.length > 0 && (
                    <Text type="supporting">
                      Langue de {spaces.map((s) => s.name).join(", ")}
                    </Text>
                  )}
                  {state.kind === "failed" && (
                    <Text type="supporting" color="primary">
                      {state.error}
                    </Text>
                  )}
                </div>
                {state.kind === "downloading" ? (
                  <div className="cl-models__progress">
                    <ProgressBar
                      label={`Téléchargement de ${theLanguage(l.label)}`}
                      value={downloadPercent(state.done, state.total)}
                      hasValueLabel
                    />
                    <Text type="supporting">
                      {gigabytes(state.done)} sur {gigabytes(state.total)}
                    </Text>
                  </div>
                ) : state.kind === "installed" ? (
                  <Text type="supporting">Installé</Text>
                ) : (
                  <span />
                )}
                <div className="cl-models__actions">
                  {canRemoveLanguage(l) && (
                    <Button
                      label="Supprimer"
                      size="sm"
                      variant="ghost"
                      isDisabled={working}
                      onClick={() => setRemoving(l)}
                    />
                  )}
                  {state.kind === "downloading" && (
                    <Button
                      label="Arrêter"
                      size="sm"
                      variant="ghost"
                      isDisabled={working}
                      onClick={() =>
                        void act(async () => {
                          for (const a of l.downloads.filter(
                            (d) => d.state === "running",
                          ))
                            await api.cancelModelAction("model", a.name);
                        })
                      }
                    />
                  )}
                  {(state.kind === "missing" || state.kind === "failed") && (
                    <Button
                      label={`${state.kind === "failed" ? "Réessayer" : "Ajouter"} · ${gigabytes(l.download_bytes)}`}
                      size="sm"
                      isDisabled={working}
                      onClick={() => setAdding(l)}
                    />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

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
