import { useCallback, useEffect, useRef, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Text } from "@astryxdesign/core/Text";
import {
  api,
  type EnvironmentInfo,
  type ModelAction,
  type ModelsView,
} from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { lastModelsView, stepsChanged } from "../steps.ts";
import {
  environmentState,
  interpreterNote,
  missingEnvironments,
  gigabytes,
  modelRows,
  percent,
  quietRows,
  readinessLine,
  sizeOf,
  removableEnvironment,
  uvStoreRows,
  type ModelRow,
  type StepLine,
} from "../models.ts";

type Asking =
  | { what: "download" | "remove"; row: ModelRow }
  | { what: "install"; name: string }
  | { what: "removeEnvironment"; env: EnvironmentInfo }
  | null;

/** The engine's models (spec §7.12, ADR 0036): what the processing needs, what is on the
 *  disk (outside the catalog too), and the explicit actions: download (the one use of the
 *  network, said before it starts), stop, remove (confirmed). Followed live while something
 *  downloads. Outside developer mode (ADR 0051), what is in use and sound is one line per
 *  step, without names, paths or Python; every other piece keeps its row and its action. */
export function ModelsSection({ onReplace }: { onReplace?: () => void }) {
  const dev = useDevMode();
  // The last reading at once, read again behind: the skeleton only before the first one.
  const [view, setView] = useState<ModelsView | null>(lastModelsView);
  const [actions, setActions] = useState<ModelAction[]>(
    () => lastModelsView()?.actions ?? [],
  );
  const [unreadable, setUnreadable] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [asking, setAsking] = useState<Asking>(null);
  const [working, setWorking] = useState(false);
  const running = useRef(new Set<string>());

  const load = useCallback(async () => {
    try {
      const next = await api.engineModels();
      setView(next);
      setActions(next.actions);
      setUnreadable(null);
      stepsChanged(next);
    } catch (e) {
      // Never the last reading under the error, as if it were current (P8).
      setView(null);
      setUnreadable((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  // While something downloads: its progress, twice a second; the whole view again once it
  // ends (what is on the disk changed).
  const busy = actions.some((a) => a.state === "running");
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.modelActions();
        setActions(next);
        const ended = [...running.current].filter(
          (id) =>
            !next.some(
              (a) => a.state === "running" && `${a.kind}:${a.name}` === id,
            ),
        );
        if (ended.length) void load();
      } catch (e) {
        setUnreadable((e as Error).message);
      }
    }, 500);
    return () => window.clearInterval(timer);
  }, [busy, load]);
  useEffect(() => {
    running.current = new Set(
      actions
        .filter((a) => a.state === "running")
        .map((a) => `${a.kind}:${a.name}`),
    );
  }, [actions]);

  const act = async (action: () => Promise<unknown>) => {
    setWorking(true);
    try {
      await action();
      setAsking(null);
      await load();
    } catch (e) {
      setRefused((e as Error).message);
      setAsking(null);
    } finally {
      setWorking(false);
    }
  };

  const rows = view ? modelRows(view, actions) : [];
  const purposeOfKey = (key: string) =>
    rows.find((r) => r.key === key)?.purpose;
  const lacking = view
    ? readinessLine(
        view.readiness,
        view.inventory,
        dev ? undefined : purposeOfKey,
      )
    : null;
  const quiet = view && !dev ? quietRows(rows, view.inventory) : null;
  const shownRows = quiet ? quiet.apart : rows;
  const environments = quiet
    ? quiet.apartEnvironments
    : (view?.inventory.environments ?? []);
  const missing = view
    ? missingEnvironments(view.readiness, view.inventory)
    : [];
  /** A model as the confirmations say it: by what it is for, its key in developer mode. */
  const named = (row: ModelRow) =>
    dev
      ? row.key
      : row.required
        ? `Le modèle « ${row.purpose} »`
        : `L'ancien modèle « ${row.purpose} »`;
  /** Installed models of this step the processing no longer uses (outside developer mode). */
  const oldOf = (purpose: string) => quiet?.old.get(purpose) ?? [];

  const stepLine = (step: StepLine) => {
    const old = oldOf(step.purpose);
    return (
      <li key={`etape-${step.purpose}`} className="cl-models__row">
        <div className="cl-models__what">
          <Text weight="medium">{step.purpose}</Text>
          {old.length > 0 && (
            <Text type="supporting">
              {old.length > 1
                ? "Les anciens modèles prennent"
                : "L'ancien modèle prend"}{" "}
              encore {gigabytes(sizeOf(old))} : le traitement ne s'en sert plus.
            </Text>
          )}
        </div>
        <Text type="supporting">Installé · {gigabytes(step.size)}</Text>
        <div className="cl-models__actions">
          {old.length > 0 && (
            <Button
              label="Supprimer l'ancien"
              size="sm"
              onClick={() => setAsking({ what: "remove", row: old[0] })}
              isDisabled={working}
            />
          )}
        </div>
      </li>
    );
  };
  const modelRow = (row: ModelRow) => (
    <li key={row.key} className="cl-models__row">
      <div className="cl-models__what">
        <Text weight="medium">{row.purpose}</Text>
        <Text type="supporting">
          {dev
            ? `${row.key}${row.required ? " · nécessaire au traitement" : ""}`
            : row.required
              ? oldOf(row.purpose).length > 0
                ? onReplace && row.state.kind === "missing"
                  ? `Remplace l'ancien modèle, qui libérera ${gigabytes(sizeOf(oldOf(row.purpose)))}`
                  : `Nécessaire au traitement ; l'ancien (${gigabytes(sizeOf(oldOf(row.purpose)))}) pourra ensuite être supprimé`
                : "Nécessaire au traitement"
              : "Facultatif : le traitement ne s'en sert pas"}
        </Text>
        {dev && row.model && (
          <Text type="supporting">
            {row.model.description} {row.model.repo}@
            {row.model.revision.slice(0, 12)} · {row.model.licence}
          </Text>
        )}
      </div>
      <ModelStateText row={row} dev={dev} />
      <div className="cl-models__actions">
        {/* The new one missing while the old one is there: replaced in one go, by
                      the window of ADR 0049 (download, then removal). */}
        {!dev &&
        onReplace &&
        row.required &&
        row.state.kind === "missing" &&
        oldOf(row.purpose).length > 0 ? (
          <Button
            label="Remplacer…"
            size="sm"
            variant="primary"
            onClick={onReplace}
            isDisabled={working}
          />
        ) : (
          <ModelActions
            row={row}
            working={working}
            onDownload={() => setAsking({ what: "download", row })}
            onRemove={() => setAsking({ what: "remove", row })}
            onCancel={() =>
              void act(() => api.cancelModelAction("model", row.key))
            }
          />
        )}
      </div>
      {row.last && row.last.state !== "done" && (
        <Said
          action={row.last}
          dev={dev}
          onRead={() => void act(() => api.forgetModelAction("model", row.key))}
        />
      )}
    </li>
  );

  return (
    <section className="cl-settings__section">
      <Heading level={3}>Traitement des séances</Heading>
      {unreadable && (
        <Banner
          status="error"
          title="Les modèles n'ont pas pu être lus"
          description={unreadable}
        />
      )}
      {refused && (
        <Banner
          status="error"
          title="Refusé"
          description={refused}
          isDismissable
          onDismiss={() => setRefused(null)}
        />
      )}
      {view === null && !unreadable && <ModelsSkeleton dev={dev} />}
      {view && (
        <>
          {lacking ? (
            <Banner
              status="warning"
              title="Il manque de quoi traiter"
              description={lacking}
            />
          ) : (
            <Text color="secondary">
              Tout est prêt pour traiter les séances :{" "}
              {gigabytes(view.inventory.total_bytes)} sur ce Mac. Rien ne se
              télécharge sans que vous le demandiez.
            </Text>
          )}
          <ul className="cl-models">
            {/* In the catalog's order: a step's line, or its own rows when it lacks something. */}
            {[...new Set(rows.map((r) => r.purpose))].flatMap((purpose) => [
              ...(quiet?.steps.filter((s) => s.purpose === purpose) ?? []).map(
                stepLine,
              ),
              ...shownRows.filter((r) => r.purpose === purpose).map(modelRow),
            ])}
            {environments.map((env) => (
              <li key={env.path} className="cl-models__row">
                <div className="cl-models__what">
                  <Text weight="medium">
                    {dev ? "Environnement de calcul" : "Outils de calcul"}
                  </Text>
                  {dev && (
                    <Text type="supporting">{env.label || env.name}</Text>
                  )}
                  {dev && <Text type="supporting">{env.name}</Text>}
                  {dev && <Text type="supporting">{env.path}</Text>}
                </div>
                <div className="cl-models__what">
                  <Text type="supporting">
                    {environmentState(env)} · {gigabytes(env.size_bytes)}
                  </Text>
                  {dev && interpreterNote(env) && (
                    <Text type="supporting">
                      {interpreterNote(env)}
                      {dev && env.interpreter ? ` (${env.interpreter})` : ""}
                    </Text>
                  )}
                </div>
                <div className="cl-models__actions">
                  {/* Only one that is not the processing's: an older lock's, or interrupted. */}
                  {removableEnvironment(env, actions) && (
                    <Button
                      label="Supprimer"
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setAsking({ what: "removeEnvironment", env })
                      }
                      isDisabled={working}
                    />
                  )}
                </div>
              </li>
            ))}
            {view &&
              dev &&
              uvStoreRows(view.inventory).map(({ key, title, note, store }) => (
                <li key={key} className="cl-models__row">
                  <div className="cl-models__what">
                    <Text weight="medium">{title}</Text>
                    <Text type="supporting">{note}</Text>
                    {dev && <Text type="supporting">{store.path}</Text>}
                  </div>
                  <Text type="supporting">{gigabytes(store.size_bytes)}</Text>
                  <div className="cl-models__actions" />
                </li>
              ))}
            {missing.map(([name, label]) => {
              const action = actions.find(
                (a) => a.kind === "environment" && a.name === name,
              );
              return (
                <li key={`manque-${name}`} className="cl-models__row">
                  <div className="cl-models__what">
                    <Text weight="medium">
                      {dev ? "Environnement de calcul" : "Outils de calcul"}
                    </Text>
                    <Text type="supporting">
                      {dev
                        ? `${label || name} · nécessaire au traitement`
                        : "Nécessaire au traitement"}
                    </Text>
                    {dev && <Text type="supporting">{name}</Text>}
                  </div>
                  <Text type="supporting">
                    {action?.state === "running"
                      ? `Installation… ${gigabytes(action.done_bytes)}`
                      : "Pas installé"}
                  </Text>
                  <div className="cl-models__actions">
                    {action?.state === "running" ? (
                      <Button
                        label="Arrêter"
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          void act(() =>
                            api.cancelModelAction("environment", name),
                          )
                        }
                      />
                    ) : (
                      <Button
                        label="Installer"
                        size="sm"
                        onClick={() => setAsking({ what: "install", name })}
                        isDisabled={working}
                      />
                    )}
                  </div>
                  {action &&
                    action.state !== "running" &&
                    action.state !== "done" && (
                      <Said
                        action={action}
                        dev={dev}
                        onRead={() =>
                          void act(() =>
                            api.forgetModelAction("environment", name),
                          )
                        }
                      />
                    )}
                </li>
              );
            })}
            {quiet && quiet.tools !== null && (
              <li className="cl-models__row">
                <div className="cl-models__what">
                  <Text weight="medium">Outils de calcul</Text>
                </div>
                <Text type="supporting">
                  Installés · {gigabytes(quiet.tools)}
                </Text>
                <div className="cl-models__actions" />
              </li>
            )}

          </ul>
        </>
      )}

      <AlertDialog
        isOpen={asking?.what === "download"}
        onOpenChange={(open) => !open && setAsking(null)}
        title="Télécharger ce modèle ?"
        description={
          asking?.what === "download" && asking.row.model
            ? `${dev ? `${asking.row.purpose} (${asking.row.key})` : `Le modèle « ${asking.row.purpose} »`} : environ ${gigabytes(asking.row.model.announced_bytes)} depuis internet${dev ? ` (${asking.row.model.repo})` : ""}. Coulisses n'utilise internet que pour cela, et pour ses mises à jour si vous l'acceptez. Vous pouvez l'arrêter : il reprendra là où il s'est arrêté.`
            : ""
        }
        actionLabel="Télécharger"
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={() => {
          if (asking?.what === "download")
            void act(() => api.downloadModel(asking.row.key));
        }}
      />
      <AlertDialog
        isOpen={asking?.what === "install"}
        onOpenChange={(open) => !open && setAsking(null)}
        title={
          dev
            ? "Installer cet environnement ?"
            : "Installer les outils de calcul ?"
        }
        description="Ils sont téléchargés depuis internet, une fois. Coulisses n'utilise internet que pour cela, et pour ses mises à jour si vous l'acceptez."
        actionLabel="Installer"
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={() => {
          if (asking?.what === "install")
            void act(() => api.installEnvironment(asking.name));
        }}
      />
      <AlertDialog
        isOpen={asking?.what === "removeEnvironment"}
        onOpenChange={(open) => !open && setAsking(null)}
        title={
          dev
            ? "Supprimer cet environnement ?"
            : "Supprimer cette ancienne version des outils de calcul ?"
        }
        description={
          asking?.what === "removeEnvironment"
            ? `${asking.env.current ? "Son installation a été interrompue" : "C'est une ancienne version"} : le traitement ne s'en sert pas. ${gigabytes(asking.env.size_bytes)} sont libérés.`
            : ""
        }
        actionLabel="Supprimer"
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={() => {
          if (asking?.what === "removeEnvironment")
            void act(() => api.removeEnvironment(asking.env.path));
        }}
      />
      <AlertDialog
        isOpen={asking?.what === "remove"}
        onOpenChange={(open) => !open && setAsking(null)}
        title={
          asking?.what === "remove" && asking.row.state.kind === "partial"
            ? "Jeter ce téléchargement ?"
            : "Supprimer ce modèle ?"
        }
        description={
          asking?.what === "remove"
            ? `${named(asking.row)} est supprimé de ce Mac${asking.row.state.kind === "partial" ? " (la partie déjà téléchargée)" : ""}.${asking.row.state.kind === "installed" && asking.row.state.replacement ? ` Il a été remplacé : le traitement ne s'en sert plus. ${gigabytes(asking.row.state.size)} sont libérés.` : ""}${asking.row.required ? " Le traitement en a besoin : les séances ne pourront plus être traitées tant qu'il n'est pas retéléchargé." : ""}`
            : ""
        }
        actionLabel="Supprimer"
        cancelLabel="Annuler"
        isActionLoading={working}
        onAction={() => {
          if (asking?.what === "remove")
            void act(() => api.removeModel(asking.row.key));
        }}
      />
    </section>
  );
}

/** What a download or an install that did not end well said, until read. */
function Said({
  action,
  dev,
  onRead,
}: {
  action: ModelAction;
  dev: boolean;
  onRead: () => void;
}) {
  return (
    <div className="cl-models__said">
      <Text
        type="supporting"
        color={action.state === "failed" ? "primary" : "secondary"}
      >
        {action.error}
        {dev && action.detail ? ` (${action.detail})` : ""}
      </Text>
      {action.terms_url && (
        <a href={action.terms_url} target="_blank" rel="noreferrer">
          Ouvrir la page des conditions
        </a>
      )}
      <Button label="Compris" variant="ghost" size="sm" onClick={onRead} />
    </div>
  );
}

function ModelStateText({ row, dev }: { row: ModelRow; dev: boolean }) {
  const state = row.state;
  switch (state.kind) {
    case "running": {
      const share = percent(state.action);
      return (
        <div className="cl-models__progress">
          <ProgressBar
            label="Téléchargement"
            value={share ?? 0}
            hasValueLabel={share !== null}
          />
          <Text type="supporting">
            {gigabytes(state.action.done_bytes)}
            {state.action.total_bytes
              ? ` sur ${gigabytes(state.action.total_bytes)}`
              : ""}
          </Text>
        </div>
      );
    }
    case "installed":
      // Replaced (ADR 0049): it only takes space, the engine says why.
      if (state.replacement)
        return (
          <div className="cl-models__what">
            <Text type="supporting" weight="medium">
              Remplacé, ne sert plus · {gigabytes(state.size)}
            </Text>
            {state.replacement.note && (
              <Text type="supporting">{state.replacement.note}</Text>
            )}
          </div>
        );
      return (
        <Text type="supporting">
          Installé · {gigabytes(state.size)}
          {state.outdated ? " · une version plus récente existe" : ""}
        </Text>
      );
    case "altered":
      return (
        <Text type="supporting">
          Abîmé ou inconnu : supprimez-le
          {row.model ? ", puis retéléchargez-le" : ""} · {gigabytes(state.size)}
          {dev && state.problem ? ` (${state.problem})` : ""}
        </Text>
      );
    case "partial":
      return (
        <Text type="supporting">
          Téléchargement interrompu · {gigabytes(state.done)} déjà là
        </Text>
      );
    case "missing":
      return (
        <Text type="supporting">
          Pas installé
          {row.model ? ` · ${gigabytes(row.model.announced_bytes)}` : ""}
        </Text>
      );
  }
}

function ModelActions({
  row,
  working,
  onDownload,
  onRemove,
  onCancel,
}: {
  row: ModelRow;
  working: boolean;
  onDownload: () => void;
  onRemove: () => void;
  onCancel: () => void;
}) {
  const remove = (
    <Button
      label="Supprimer"
      size="sm"
      variant="ghost"
      onClick={onRemove}
      isDisabled={working}
    />
  );
  switch (row.state.kind) {
    case "running":
      return (
        <Button label="Arrêter" size="sm" variant="ghost" onClick={onCancel} />
      );
    case "installed":
      // A replaced model's removal is put forward (still confirmed: P8).
      return row.state.replacement ? (
        <Button
          label="Supprimer"
          size="sm"
          variant="primary"
          onClick={onRemove}
          isDisabled={working}
        />
      ) : (
        remove
      );
    case "altered":
      return remove;
    case "partial":
      return (
        <>
          {row.model && (
            <Button
              label="Reprendre"
              size="sm"
              onClick={onDownload}
              isDisabled={working}
            />
          )}
          {remove}
        </>
      );
    case "missing":
      return row.model ? (
        <Button
          label="Télécharger"
          size="sm"
          onClick={onDownload}
          isDisabled={working}
        />
      ) : null;
  }
}

/** While the engine reads what is on the disk (sizes, a second or so): the list's shapes,
 *  the rows it usually has (one per step outside developer mode, one per model in it). */
function ModelsSkeleton({ dev }: { dev: boolean }) {
  return (
    <div
      className="cl-skeleton"
      aria-busy="true"
      aria-label="Lecture des modèles"
    >
      <div className="cl-skeleton__text cl-skeleton__text--flush">
        <Skeleton width="100%" height={12} radius={1} />
        <Skeleton width="70%" height={12} radius={1} />
      </div>
      <ul className="cl-models">
        {[0.5, 0.42, 0.56, 0.38, 0.47, 0.44]
          .slice(0, dev ? 6 : 5)
          .map((w, i) => (
            <li key={i} className="cl-models__row">
              <div className="cl-models__what">
                <Skeleton
                  width={`${w * 100}%`}
                  height={14}
                  radius={1}
                  index={i}
                />
                {dev && (
                  <Skeleton width="35%" height={11} radius={1} index={i} />
                )}
              </div>
              <Skeleton width="45%" height={11} radius={1} index={i} />
              <div className="cl-models__actions">
                {dev && (
                  <Skeleton width={84} height={28} radius={2} index={i} />
                )}
              </div>
            </li>
          ))}
      </ul>
    </div>
  );
}
