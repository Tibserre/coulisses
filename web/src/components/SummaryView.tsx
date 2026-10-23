import { useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Markdown } from "@astryxdesign/core/Markdown";
import { Popover } from "@astryxdesign/core/Popover";
import { Text } from "@astryxdesign/core/Text";
import { Check, Copy, Download, Plus, RefreshCw } from "lucide-react";
import {
  api,
  type ActionInfo,
  type Generation,
  type Generations,
  type SpaceAction,
} from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { formatDateTime, formatDuration } from "../format.ts";
import { inertMarkdown } from "../inertMarkdown.ts";
import { summaryTabs, writable, type SummaryTab } from "../summaries.ts";

/** Nothing a generated text points to is ever fetched or opened (P1): images show their
 *  description, links their text. The parser's own forms (references included) all go
 *  through these renderers. */
const SAFE_RENDERERS = {
  image: ({ alt }: { src: string; alt: string }) => <>{alt}</>,
  link: ({ children }: { href: string; children: React.ReactNode }) => (
    <>{children}</>
  ),
};

function SummaryText({ output }: { output: string }) {
  return (
    <div className="cl-summary__body">
      <Markdown
        headingLevelStart={3}
        contentWidth="100%"
        components={SAFE_RENDERERS}
      >
        {output}
      </Markdown>
    </div>
  );
}

/** The « Résumé » view (ADR 0060): one tab per summary written, its latest version, and
 *  « + Rédiger… » for another. « Refaire » makes it again with the model of Réglages ›
 *  Rédaction; « Revenir à la version d'avant » brings the one before back, once. Every
 *  version stays on the disk (P5); all of them, side by side, in developer mode.
 *  `transcriptKey` changes with the corrections in force (or a new run): staleness is
 *  computed by the service, so the list is asked again each time. */
export function SummaryView({
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
  const [reachable, setReachable] = useState(true);
  /** The space's settings: the summary it offers first (the Résumé Impro for a troupe). */
  const [spacePrefs, setSpacePrefs] = useState<SpaceAction[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    api.models().then(
      (m) => setReachable(m.reachable),
      (e: Error) => setError(e.message),
    );
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

  const preferred = spacePrefs.find((a) => a.auto_run)?.action_ref ?? null;
  const tabs = data
    ? summaryTabs(data.generations, data.pending, preferred)
    : [];
  const tab = tabs.find((t) => t.ref === current) ?? tabs[0] ?? null;
  const offered = writable(actions, tabs, preferred);

  /** Written with the model of Réglages › Rédaction (ADR 0060). */
  const write = async (ref: string) => {
    setAdding(false);
    setCurrent(ref);
    try {
      setData(await api.requestGeneration(sessionId, ref, null));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // Not read yet: nothing, or why it could not be (P8).
  if (!data)
    return error ? (
      <Banner status="error" title="Résumé" description={error} />
    ) : null;
  const others = (
    <ul className="cl-namepanel__list">
      {offered.map((a) => (
        <li key={a.ref}>
          <button
            type="button"
            className="cl-namepanel__person"
            onClick={() => void write(a.ref)}
          >
            <span />
            <span>{a.name}</span>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="cl-summary">
      {error && <Banner status="error" title="Résumé" description={error} />}
      {!reachable && (
        <Banner
          status="warning"
          title="Ollama ne répond pas"
          description="Lancez l'application Ollama pour rédiger un résumé. Les résumés déjà faits restent lisibles."
        />
      )}

      {tabs.length === 0 ? (
        <div className="cl-summary__empty">
          <Text weight="medium">Pas encore de résumé</Text>
          <Text type="supporting" as="p">
            Rédigé sur ce Mac par le modèle choisi dans Réglages › Rédaction.
          </Text>
          {offered[0] && (
            <Button
              label={`Rédiger : ${offered[0].name}`}
              variant="primary"
              isDisabled={!reachable}
              clickAction={() => write(offered[0].ref)}
            />
          )}
          {offered.length > 1 && (
            <Popover
              isOpen={adding}
              onOpenChange={setAdding}
              label="Rédiger un autre résumé"
              width={280}
              content={others}
            >
              <button type="button" className="cl-linkbtn">
                ou un autre résumé
              </button>
            </Popover>
          )}
        </div>
      ) : (
        <>
          <div className="cl-sumtabs" role="tablist" aria-label="Résumés">
            {tabs.map((t) => (
              <button
                key={t.ref}
                type="button"
                role="tab"
                className="cl-sumtabs__tab"
                aria-selected={t.ref === tab?.ref}
                onClick={() => setCurrent(t.ref)}
              >
                {t.name}
              </button>
            ))}
            {offered.length > 0 && (
              <Popover
                isOpen={adding}
                onOpenChange={setAdding}
                label="Rédiger un autre résumé"
                width={280}
                content={others}
              >
                <button
                  type="button"
                  className="cl-sumtabs__tab"
                  data-add
                  disabled={!reachable}
                >
                  <Plus size={14} strokeWidth={1.75} aria-hidden />
                  Rédiger…
                </button>
              </Popover>
            )}
          </div>
          {tab && (
            <SummaryTabBody
              key={tab.ref}
              sessionId={sessionId}
              tab={tab}
              reachable={reachable}
              onWrite={() => write(tab.ref)}
              onChanged={setData}
              onError={setError}
            />
          )}
        </>
      )}
      {dev && data.generations.length > 1 && (
        <AllVersions generations={data.generations} />
      )}
    </div>
  );
}

function SummaryTabBody({
  sessionId,
  tab,
  reachable,
  onWrite,
  onChanged,
  onError,
}: {
  sessionId: string;
  tab: SummaryTab;
  reachable: boolean;
  onWrite: () => Promise<void>;
  onChanged: (next: Generations) => void;
  onError: (message: string) => void;
}) {
  const dev = useDevMode();
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [prompts, setPrompts] = useState<string | null>(null);
  const shown = tab.latest;
  const pending = tab.pending;
  const writing =
    pending !== null &&
    (pending.state === "queued" || pending.state === "running");

  const copy = async () => {
    if (!shown?.output) return;
    try {
      await navigator.clipboard.writeText(inertMarkdown(shown.output));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      onError(
        "La copie a été refusée par le navigateur : sélectionnez le texte et faites Cmd-C.",
      );
    }
  };
  const restore = async () => {
    if (!shown) return;
    try {
      onChanged(await api.restoreGeneration(sessionId, shown.id));
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <article className="cl-summary__doc">
      {pending?.state === "failed" && (
        <Banner
          status="error"
          title={`${tab.name} : la rédaction a échoué`}
          description={pending.error ?? "Erreur inconnue."}
          endContent={
            <Button size="sm" label="Relancer" clickAction={onWrite} />
          }
        />
      )}
      {writing && (
        // Said, not spun (nothing moves in a loop, art direction): its shapes, still.
        <div className="cl-summary__writing" role="status">
          <Text type="supporting">
            {pending.state === "queued"
              ? `« ${tab.name} » attend son tour : un autre texte s'écrit d'abord.`
              : shown
                ? `Une nouvelle version de « ${tab.name} » s'écrit · celle-ci reste lisible en attendant.`
                : `« ${tab.name} » s'écrit · vous pouvez relire la transcription en attendant.`}
          </Text>
          {!shown && (
            <div className="cl-summary__lines" aria-hidden>
              <i />
              <i />
              <i />
            </div>
          )}
        </div>
      )}
      {shown && (
        <>
          <header className="cl-summary__head">
            <Text type="supporting" as="p">
              {shown.restored ? "Version d'avant, revenue · " : ""}
              Rédigé le {formatDateTime(shown.created_at)}
              {dev
                ? ` · ${shown.model} · ${formatDuration(shown.duration_s)}`
                : ""}
              {shown.strategy === "sections"
                ? " · résumé par parties, puis fusionné"
                : ""}
            </Text>
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
              {!writing && !shown.stale && (
                <Button
                  size="sm"
                  variant="ghost"
                  label="Refaire"
                  icon={<RefreshCw size={14} strokeWidth={1.75} />}
                  isDisabled={!reachable}
                  clickAction={onWrite}
                />
              )}
            </div>
          </header>
          {shown.restorable && !writing && (
            <Text type="supporting" as="p">
              Refait ·{" "}
              <button
                type="button"
                className="cl-linkbtn"
                onClick={() => void restore()}
              >
                Revenir à la version d'avant
              </button>
            </Text>
          )}
          {shown.problem && (
            <Banner
              status="warning"
              title="Résumé incomplet"
              description={shown.problem}
            />
          )}
          {shown.stale && !writing && (
            <div className="cl-summary__stale">
              <Text type="supporting">
                La séance a changé depuis ce résumé.
              </Text>
              <Button
                size="sm"
                variant="ghost"
                label="Le refaire"
                icon={<RefreshCw size={14} strokeWidth={1.75} />}
                isDisabled={!reachable}
                clickAction={onWrite}
              />
            </div>
          )}
          {shown.output ? (
            <SummaryText output={shown.output} />
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
                  onError((e as Error).message);
                }
              }}
            />
          )}
        </>
      )}
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
    </article>
  );
}

/** Developer mode: every version written, two of them side by side (ADR 0025, 0060). */
function AllVersions({ generations }: { generations: Generation[] }) {
  const [compared, setCompared] = useState<number[]>([]);
  const [comparing, setComparing] = useState(false);
  return (
    <section className="cl-summary__history">
      <Text weight="medium">Toutes les versions</Text>
      <Text type="supporting">
        Mode développeur · cochez-en deux pour les lire côte à côte.
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
              <span>
                {g.action_name}
                <Text type="supporting">
                  {" "}
                  · {formatDateTime(g.created_at)} · {g.model}
                  {g.restored ? " · revenue" : ""}
                  {g.stale ? " · périmé" : ""}
                </Text>
              </span>
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
                  <SummaryText output={g.output} />
                ) : (
                  <Text type="supporting">
                    Texte introuvable dans le dossier de la séance.
                  </Text>
                )}
              </article>
            ))}
        </div>
      </Dialog>
    </section>
  );
}
