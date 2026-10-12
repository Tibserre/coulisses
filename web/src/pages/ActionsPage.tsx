import { useCallback, useEffect, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { TextInput } from "@astryxdesign/core/TextInput";
import { api, type ActionDraft, type ActionInfo } from "../api.ts";
import { clearDraft, readDraft, writeDraft } from "../drafts.ts";
import { formatDateTime } from "../format.ts";

const NEW = "nouvelle";
const EMPTY: ActionDraft = { name: "", description: "", prompt: "" };

/** The actions (spec §7.9): the provided ones, which one can modify and restore, and the
 *  user's own. Nothing is deleted: an action of one's own is archived, and every summary
 *  keeps the exact prompt that made it. */
export function ActionsPage({ selectedRef }: { selectedRef: string | null }) {
  const [all, setAll] = useState<ActionInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAll(await api.actions());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const creating = selectedRef === NEW;
  const selected = creating
    ? null
    : (all.find((a) => a.ref === selectedRef) ?? all[0] ?? null);
  const provided = all.filter((a) => a.provided);
  const own = all.filter((a) => !a.provided);

  const item = (a: ActionInfo) => (
    <li key={a.ref}>
      <a
        href={`#/actions/${encodeURIComponent(a.ref)}`}
        aria-current={a.ref === selected?.ref ? "page" : undefined}
      >
        {a.name}
        {a.modified && <Text type="supporting"> · modifiée</Text>}
      </a>
    </li>
  );

  return (
    <div className="cl-page">
      <main className="cl-spaces">
        <aside className="cl-spaces__list">
          <Heading level={2}>Actions de résumé</Heading>
          <Text type="supporting">Fournies avec Coulisses</Text>
          <ul>{provided.map(item)}</ul>
          {own.length > 0 && (
            <>
              <Text type="supporting">Les vôtres</Text>
              <ul>{own.map(item)}</ul>
            </>
          )}
          <Button
            label="Nouvelle action"
            onClick={() => {
              window.location.hash = `#/actions/${NEW}`;
            }}
          />
        </aside>
        <section className="cl-spaces__detail">
          {error && (
            <Banner status="error" title="Refusé" description={error} />
          )}
          {(creating || selected) && (
            <ActionEditor
              key={
                creating
                  ? NEW
                  : `${selected!.ref}:${selected!.updated_at ?? ""}:${selected!.modified}`
              }
              action={creating ? null : selected}
              onSaved={async (ref) => {
                await load();
                window.location.hash = `#/actions/${encodeURIComponent(ref)}`;
              }}
              onArchived={async () => {
                await load();
                window.location.hash = "#/actions";
              }}
              onError={setError}
            />
          )}
        </section>
      </main>
    </div>
  );
}

function ActionEditor({
  action,
  onSaved,
  onArchived,
  onError,
}: {
  /** null: a new action. */
  action: ActionInfo | null;
  onSaved: (ref: string) => Promise<void>;
  onArchived: () => Promise<void>;
  onError: (message: string | null) => void;
}) {
  const initial: ActionDraft = action
    ? {
        name: action.name,
        description: action.description,
        prompt: action.prompt,
      }
    : EMPTY;
  // A draft not saved is kept in this browser: going to another action or closing the
  // window does not lose it (P8); it comes back here, said so.
  const draftKey = `action:${action?.ref ?? NEW}`;
  const [draft, setDraftState] = useState<ActionDraft>(
    () => readDraft<ActionDraft>(draftKey) ?? initial,
  );
  const [confirm, setConfirm] = useState<"restore" | "archive" | null>(null);
  const changed =
    draft.name !== initial.name ||
    draft.description !== initial.description ||
    draft.prompt !== initial.prompt;
  const [recovered] = useState(changed);
  const setDraft = (next: ActionDraft) => {
    setDraftState(next);
    writeDraft(draftKey, next);
  };
  const forget = () => {
    clearDraft(draftKey);
    setDraftState(initial);
  };
  useEffect(() => {
    if (!changed) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changed]);

  const run = (step: () => Promise<unknown>) => async () => {
    try {
      await step();
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    }
  };
  const save = run(async () => {
    const saved = action
      ? await api.updateAction(action.ref, draft)
      : await api.createAction(draft);
    clearDraft(draftKey);
    await onSaved(saved.ref);
  });

  return (
    <div className="cl-space">
      <div className="cl-space__head">
        <Heading level={2}>{action ? action.name : "Nouvelle action"}</Heading>
        <Text type="supporting">
          {action == null
            ? "Une action à vous, que vous pourrez lancer sur toutes les séances."
            : action.modified
              ? `Action fournie, modifiée${action.updated_at ? ` le ${formatDateTime(action.updated_at)}` : ""}. L'original reste restaurable.`
              : action.provided
                ? "Action fournie avec Coulisses. La modifier crée votre version ; l'original reste restaurable."
                : `Action à vous${action.updated_at ? `, modifiée le ${formatDateTime(action.updated_at)}` : ""}.`}
        </Text>
      </div>
      {recovered && changed && (
        <Banner
          status="warning"
          title="Brouillon retrouvé"
          description="Ces changements n'ont pas été enregistrés : enregistrez-les ou annulez-les."
        />
      )}
      <section className="cl-space__section">
        <TextInput
          label="Nom"
          value={draft.name}
          onChange={(name) => setDraft({ ...draft, name })}
         
        />
        <TextInput
          label="Description"
          description="Ce que produit l'action, en une phrase : elle s'affiche au moment de choisir."
          value={draft.description}
          onChange={(description) => setDraft({ ...draft, description })}

        />
        <TextArea
          label="Prompt"
          description="Coulisses ajoute toujours autour : le cadre, la règle pour une séance sans contenu, la consigne de répondre en français, le contexte (espace, présents, voix, glossaire, notes) et la transcription avec ses chapitres. Ne les recopiez pas."
          value={draft.prompt}
          onChange={(prompt) => setDraft({ ...draft, prompt })}
          rows={22}
          hasSpellCheck
        />
        <div className="cl-actions__buttons">
          <Button
            label={action ? "Enregistrer" : "Créer l'action"}
            variant="primary"
            isDisabled={!changed || !draft.name.trim() || !draft.prompt.trim()}
            clickAction={save}
          />
          {changed && action && (
            <Button
              label="Annuler les changements"
              variant="ghost"
              onClick={forget}
            />
          )}
          {action && (
            <Button
              label="Dupliquer"
              variant="ghost"
              clickAction={run(async () => {
                const copy = await api.duplicateAction(action.ref);
                await onSaved(copy.ref);
              })}
            />
          )}
          {action?.modified && (
            <Button
              label="Restaurer l'original"
              variant="ghost"
              onClick={() => setConfirm("restore")}
            />
          )}
          {action && !action.provided && (
            <Button
              label="Retirer l'action"
              variant="ghost"
              onClick={() => setConfirm("archive")}
            />
          )}
        </div>
      </section>
      {action && (
        <AlertDialog
          isOpen={confirm !== null}
          onOpenChange={(open) => !open && setConfirm(null)}
          title={
            confirm === "restore"
              ? "Restaurer l'original ?"
              : "Retirer cette action ?"
          }
          description={
            confirm === "restore"
              ? "Votre version n'est plus utilisée ; elle reste gardée dans la base. Les résumés déjà faits gardent le prompt qui les a produits."
              : "Elle disparaît des listes et n'est plus proposée. Les résumés déjà faits avec elle restent, avec leur prompt."
          }
          actionLabel={confirm === "restore" ? "Restaurer" : "Retirer"}
          cancelLabel="Annuler"
          onAction={run(async () => {
            if (confirm === "restore") {
              await api.restoreAction(action.ref);
              clearDraft(draftKey); // back to the original: the draft on it goes too
              setConfirm(null);
              await onSaved(action.ref);
            } else {
              await api.archiveAction(action.ref);
              setConfirm(null);
              await onArchived();
            }
          })}
        />
      )}
    </div>
  );
}
