import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Markdown } from "@astryxdesign/core/Markdown";
import { Popover } from "@astryxdesign/core/Popover";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { Check, Copy, Download, RefreshCw } from "lucide-react";
import {
  api,
  type ActionInfo,
  type Generation,
  type Generations,
  type ModelsInfo,
  type SpaceAction,
} from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { formatDateTime, formatDuration } from "../format.ts";
import { inertMarkdown } from "../inertMarkdown.ts";

/** Nothing a generated text points to is ever fetched or opened (P1): images show their
 *  description, links their text. The parser's own forms (references included) all go
 *  through these renderers. */
const SAFE_RENDERERS = {
  image: ({ alt }: { src: string; alt: string }) => <>{alt}</>,
  link: ({ children }: { href: string; children: React.ReactNode }) => (
    <>{children}</>
  ),
};

/** The model to use: the default chosen last, or the first installed one. */
function ModelSelect({
  info,
  value,
  onChange,
}: {
  info: ModelsInfo | null;
  value: string | null;
  onChange: (model: string) => void;
}) {
  if (!info) return null;
  const names = info.models.map((m) => m.name);
  const current = value ?? info.default;
  const options = names.includes(current) ? names : [current, ...names];
  return (
    <label className="cl-select">
      <span>Modèle</span>
      <select value={current} onChange={(e) => onChange(e.target.value)}>
        {options.map((name) => (
          <option key={name} value={name}>
            {name}
            {!names.includes(name) ? " (absent d'Ollama)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

/** The « Résumé » tab: the latest summary, the ones before it, and how to make another.
 *  `transcriptKey` changes with the corrections in force (or a new run): staleness is computed
 *  by the service, so the list is asked again each time. */
export function SummaryPanel({
  sessionId,
  spaceId,
  transcriptKey,
}: {
  sessionId: string;
  spaceId: number;
  transcriptKey: string;
}) {
  const dev = useDevMode();
  const [data, setData] = useState<Generations | null>(null);
  const [actions, setActions] = useState<ActionInfo[]>([]);
  const [models, setModels] = useState<ModelsInfo | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [action, setAction] = useState<string | null>(null);
  const [shownId, setShownId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [prompts, setPrompts] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  /** The space's settings: the summary it offers first (the Résumé Impro for a troupe). */
  const [spacePrefs, setSpacePrefs] = useState<SpaceAction[]>([]);
  /** Two summaries to read side by side. */
  const [compared, setCompared] = useState<number[]>([]);
  const [comparing, setComparing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setData(await api.generations(sessionId));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
    api.actions().then(setActions, (e: Error) => setError(e.message));
    api.models().then(setModels, (e: Error) => setError(e.message));
    api
      .spaceActions(spaceId)
      .then(setSpacePrefs, (e: Error) => setError(e.message));
  }, [refresh, spaceId]);

  const seenKey = useRef(transcriptKey);
  useEffect(() => {
    if (seenKey.current === transcriptKey) return;
    seenKey.current = transcriptKey;
    void refresh();
  }, [transcriptKey, refresh]);

  const waiting =
    data?.pending.some((p) => p.state === "queued" || p.state === "running") ??
    false;
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [waiting, refresh]);

  const generations = data?.generations ?? [];
  const shown: Generation | undefined =
    generations.find((g) => g.id === shownId) ?? generations[0];
  const preferred = spacePrefs.find((a) => a.auto_run)?.action_ref ?? null;
  const chosenAction =
    action ?? shown?.action_ref ?? preferred ?? actions[0]?.ref ?? null;

  const generate = async (ref: string) => {
    try {
      setData(await api.requestGeneration(sessionId, ref, model));
      setShownId(null);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const copy = async () => {
    if (!shown?.output) return;
    try {
      await navigator.clipboard.writeText(inertMarkdown(shown.output));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError(
        "La copie a été refusée par le navigateur : sélectionnez le texte et faites Cmd-C.",
      );
    }
  };

  return (
    <div className="cl-summary">
      {error && <Banner status="error" title="Résumé" description={error} />}
      {models && !models.reachable && (
        <Banner
          status="warning"
          title="Ollama ne répond pas"
          description="Lancez l'application Ollama pour générer un résumé. Les résumés déjà faits restent lisibles."
        />
      )}

      {data?.pending.map((p) => (
        <div
          key={p.job_id}
          className="cl-summary__pending"
          data-state={p.state}
        >
          {p.state === "failed" ? (
            <Banner
              status="error"
              title={`${p.action_name} : échec`}
              description={p.error ?? "Erreur inconnue."}
              endContent={
                <Button
                  size="sm"
                  label="Relancer"
                  clickAction={() => generate(p.action_ref)}
                />
              }
            />
          ) : (
            <Spinner
              size="sm"
              label={`${p.action_name} ${p.state === "running" ? "en cours de rédaction" : "en attente"} · ${p.model}`}
            />
          )}
        </div>
      ))}

      {shown ? (
        <article className="cl-summary__doc">
          <header className="cl-summary__head">
            <div>
              <Text weight="medium">{shown.action_name}</Text>
              <Text type="supporting" as="p">
                {formatDateTime(shown.created_at)}
                {dev
                  ? ` · ${shown.model} · ${formatDuration(shown.duration_s)}`
                  : ""}
                {shown.strategy === "sections"
                  ? " · résumé par parties, puis fusionné"
                  : ""}
              </Text>
            </div>
            <div className="cl-summary__tools">
              <button
                type="button"
                className="cl-iconbtn"
                onClick={() => void copy()}
                aria-label="Copier le résumé"
                title="Copier le résumé"
              >
                {copied ? (
                  <Check size={15} strokeWidth={1.75} />
                ) : (
                  <Copy size={15} strokeWidth={1.75} />
                )}
              </button>
              <Popover
                isOpen={exporting}
                onOpenChange={setExporting}
                label="Exporter en Markdown"
                width={260}
                content={
                  <ul className="cl-namepanel__list">
                    {(
                      [
                        ["resume", "Le résumé"],
                        ["transcript", "La transcription"],
                        ["tout", "Le résumé et la transcription"],
                      ] as const
                    ).map(([what, label]) => (
                      <li key={what}>
                        <a
                          className="cl-namepanel__person"
                          href={api.exportUrl(sessionId, what, shown.id)}
                          onClick={() => setExporting(false)}
                        >
                          <span />
                          <span>{label}</span>
                          <Text type="supporting">.md</Text>
                        </a>
                      </li>
                    ))}
                  </ul>
                }
              >
                <button
                  type="button"
                  className="cl-iconbtn"
                  aria-label="Exporter en Markdown"
                  title="Exporter en Markdown"
                >
                  <Download size={15} strokeWidth={1.75} />
                </button>
              </Popover>
            </div>
          </header>
          {shown.problem && (
            <Banner
              status="warning"
              title="Résumé incomplet"
              description={shown.problem}
            />
          )}
          {shown.stale && (
            <div className="cl-summary__stale">
              <Text type="supporting">
                La séance a changé depuis ce résumé.
              </Text>
              <Button
                size="sm"
                variant="ghost"
                label="Le refaire"
                icon={<RefreshCw size={14} strokeWidth={1.75} />}
                clickAction={() => generate(shown.action_ref)}
              />
            </div>
          )}
          {shown.output ? (
            <div className="cl-summary__body">
              <Markdown
                headingLevelStart={3}
                contentWidth="100%"
                components={SAFE_RENDERERS}
              >
                {shown.output}
              </Markdown>
            </div>
          ) : (
            <Banner
              status="error"
              title="Résumé introuvable"
              description="Son texte (output.md) n'est plus dans le dossier de la séance : a-t-il été déplacé ou supprimé dans le Finder ?"
            />
          )}
          {dev && (
            <Button
              size="sm"
              variant="ghost"
              label="Voir les prompts envoyés"
              clickAction={async () => {
                try {
                  setPrompts(await api.generationPrompts(sessionId, shown.id));
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            />
          )}
        </article>
      ) : (
        !data?.pending.length && (
          <Text color="secondary" as="p">
            Pas encore de résumé : choisissez-en un et un modèle, puis « Générer
            ».
          </Text>
        )
      )}

      <section className="cl-summary__new">
        <Text weight="medium">Générer un résumé</Text>
        <label className="cl-select">
          <span>Résumé</span>
          <select
            value={chosenAction ?? ""}
            onChange={(e) => setAction(e.target.value)}
          >
            {actions.map((a) => (
              <option key={a.ref} value={a.ref}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        {actions.find((a) => a.ref === chosenAction) && (
          <Text type="supporting" as="p">
            {actions.find((a) => a.ref === chosenAction)!.description}
          </Text>
        )}
        <ModelSelect info={models} value={model} onChange={setModel} />
        <Button
          label="Générer"
          variant="primary"
          isDisabled={!chosenAction || (models != null && !models.reachable)}
          clickAction={() =>
            chosenAction ? generate(chosenAction) : Promise.resolve()
          }
        />
      </section>

      {generations.length > 1 && (
        <section className="cl-summary__history">
          <Text weight="medium">Historique</Text>
          <Text type="supporting">
            Cochez deux résumés pour les lire côte à côte.
          </Text>
          <ul>
            {generations.map((g) => {
              const checked = compared.includes(g.id);
              return (
                <li key={g.id}>
                  <input
                    type="checkbox"
                    className="cl-summary__pick"
                    checked={checked}
                    disabled={!checked && compared.length >= 2}
                    aria-label={`Comparer ${g.action_name} du ${formatDateTime(g.created_at)}`}
                    onChange={() =>
                      setCompared((before) =>
                        checked
                          ? before.filter((id) => id !== g.id)
                          : [...before, g.id],
                      )
                    }
                  />
                  <button
                    type="button"
                    aria-current={g.id === shown?.id ? "true" : undefined}
                    onClick={() => setShownId(g.id)}
                  >
                    {g.action_name}
                    <Text type="supporting">
                      {" "}
                      · {formatDateTime(g.created_at)}
                    </Text>
                    {g.stale && <Text type="supporting"> · périmé</Text>}
                  </button>
                </li>
              );
            })}
          </ul>
          {compared.length === 2 && (
            <Button
              size="sm"
              label="Comparer les deux"
              clickAction={() => setComparing(true)}
            />
          )}
        </section>
      )}

      <Dialog
        isOpen={comparing}
        onOpenChange={(open) => !open && setComparing(false)}
        width="min(1240px, 96vw)"
      >
        <DialogHeader
          title="Deux résumés côte à côte"
          onOpenChange={() => setComparing(false)}
        />
        <div className="cl-compare">
          {compared
            .map((id) => generations.find((g) => g.id === id))
            .filter((g): g is Generation => g !== undefined)
            .map((g) => (
              <article key={g.id} className="cl-compare__side">
                <header>
                  <Text weight="medium">{g.action_name}</Text>
                  <Text type="supporting" as="p">
                    {formatDateTime(g.created_at)} · {g.model}
                    {g.stale ? " · périmé" : ""}
                  </Text>
                </header>
                {g.output ? (
                  <div className="cl-summary__body">
                    <Markdown
                      headingLevelStart={3}
                      contentWidth="100%"
                      components={SAFE_RENDERERS}
                    >
                      {g.output}
                    </Markdown>
                  </div>
                ) : (
                  <Text type="supporting">
                    Texte introuvable dans le dossier de la séance.
                  </Text>
                )}
              </article>
            ))}
        </div>
      </Dialog>

      <Dialog
        isOpen={prompts !== null}
        onOpenChange={(open) => !open && setPrompts(null)}
        width={760}
      >
        <DialogHeader
          title="Prompts envoyés, mot pour mot"
          onOpenChange={() => setPrompts(null)}
        />
        <pre className="cl-prompts">{prompts}</pre>
      </Dialog>
    </div>
  );
}
