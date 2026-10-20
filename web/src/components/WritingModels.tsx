import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Popover } from "@astryxdesign/core/Popover";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Text } from "@astryxdesign/core/Text";
import { Check, ChevronDown } from "lucide-react";
import {
  api,
  type InstalledModel,
  type ModelsInfo,
  type Writing,
} from "../api.ts";
import { useDevMode } from "../devMode.ts";
import { formatBytes } from "../format.ts";
import { ollamaLabels } from "../ollamaNames.ts";
import {
  OLLAMA_DOWNLOAD,
  OLLAMA_LIBRARY,
  adviceStep,
  memoryUnknown,
  shortMemory,
} from "../writingAdvice.ts";

/** What each model writes, as the page says it. */
const WRITINGS: { writing: Writing; label: string; picker: string; description: string }[] = [
  {
    writing: "titre",
    label: "Titre",
    picker: "Modèle du titre",
    description: "Proposé sous le titre d'une séance, à la demande.",
  },
  {
    writing: "chapitres",
    label: "Chapitres",
    picker: "Modèle des chapitres",
    description: "Découpés après chaque traitement, ou à nouveau à la demande.",
  },
  {
    writing: "resume",
    label: "Résumés",
    picker: "Modèle des résumés",
    description:
      "Proposé d'abord dans l'onglet Résumé ; un autre s'y choisit aussi.",
  },
];

/** A model as the lists say it: its size in parameters and on the disk; its exact name in
 *  developer mode. */
function about(m: InstalledModel, dev: boolean): string {
  return [dev ? m.name : null, m.parameter_size, formatBytes(m.size_bytes)]
    .filter(Boolean)
    .join(" · ");
}

/** The language models (spec §7.12, ADR 0039): the one each writing is made with, chosen
 *  among those installed in Ollama, and those installed. Changing one applies to what is
 *  asked afterwards; what is done keeps the model that wrote it (its provenance). */
export function WritingModels() {
  const dev = useDevMode();
  const [info, setInfo] = useState<ModelsInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** A service started before this page was installed does not say each writing's model
   *  (a guard at run time: the type says it always does). Said plainly, never a broken
   *  page; the error is cleared only by a reading that has it. */
  const read = (next: ModelsInfo) => {
    if (next.writings) {
      setInfo(next);
      setError(null);
    } else
      setError(
        "Le service de Coulisses date d'avant cette page : quittez Coulisses (⌘Q) et rouvrez-le. S'il a été lancé dans le Terminal, arrêtez-le là (⌃C) et relancez-le.",
      );
  };
  useEffect(() => {
    api.models().then(read, (e: Error) => setError(e.message));
  }, []);

  const choose = async (writing: Writing, model: string) => {
    try {
      read(await api.setWritingModel(writing, model));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const [allInstalled, setAllInstalled] = useState(false);
  const used = (name: string) =>
    WRITINGS.filter((w) => info?.writings[w.writing] === name).map((w) => w.label);
  // Said as « Qwen 3.8 – 27b » (ADR 0051): the installed ones and the chosen ones together, so
  // no two read alike; the exact name in developer mode.
  const labels = ollamaLabels([
    ...(info?.models.map((m) => m.name) ?? []),
    ...Object.values(info?.writings ?? {}),
  ]);
  // The advised model may not be installed yet: said on its own then.
  const said = (name: string) =>
    dev ? name : (labels.get(name) ?? ollamaLabels([name]).get(name) ?? name);
  const installedBytes = info?.models.reduce((sum, m) => sum + m.size_bytes, 0) ?? 0;

  return (
    <>
      <section className="cl-settings__section">
        <Heading level={3}>Modèles de rédaction</Heading>
        <Text color="secondary">
          Les titres, les chapitres et les résumés sont rédigés sur ce Mac par
          un modèle de langage, dans Ollama. Un changement vaut pour la suite ;
          ce qui est rédigé garde son modèle.
        </Text>
        {error && (
          <Banner
            status="error"
            title="Lecture ou choix impossible"
            description={error}
            isDismissable
            onDismiss={() => setError(null)}
          />
        )}
        {info && <WritingAdviceBanner info={info} dev={dev} said={said} />}
        {info === null && !error ? (
          <WritingSkeleton />
        ) : (
          info && (
            <ul className="cl-writings">
              {WRITINGS.map(({ writing, label, picker, description }) => (
                <li key={writing} className="cl-writings__row">
                  <span className="cl-writings__what">
                    <span className="cl-writings__label">{label}</span>
                    <span className="cl-writings__description">{description}</span>
                  </span>
                  <ModelPicker
                    label={picker}
                    value={info.writings[writing]}
                    said={said}
                    dev={dev}
                    models={info.models}
                    reachable={info.reachable}
                    onChoose={(model) => void choose(writing, model)}
                  />
                </li>
              ))}
            </ul>
          )
        )}
      </section>

      {/* Last on the page: unfolding it moves nothing below. */}
      {info?.reachable && info.models.length > 0 && (
        <section className="cl-settings__section">
          <div className="cl-settings__line">
            <Text color="secondary">
              {info.models.length === 1
                ? "1 modèle installé dans Ollama"
                : `${info.models.length} modèles installés dans Ollama`}
              , {formatBytes(installedBytes)}
            </Text>
            <Button
              size="sm"
              variant="ghost"
              label={allInstalled ? "Masquer la liste" : "Voir la liste"}
              onClick={() => setAllInstalled(!allInstalled)}
            />
          </div>
          {allInstalled && (
            <ul className="cl-settings__list">
              {info.models.map((m) => {
                const uses = used(m.name);
                return (
                  <li key={m.name}>
                    <span className="cl-settings__text">
                      <Text>{said(m.name)}</Text>
                      <Text type="supporting">
                        {about(m, dev)}
                        {dev && m.family ? ` · ${m.family}` : ""}
                      </Text>
                    </span>
                    {uses.length > 0 && (
                      <span className="cl-writings__uses">{uses.join(", ")}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </>
  );
}

/** What gets writing going on this Mac (lot 11g of the plan): install Ollama, install the
 *  model advised for its memory, or pick one; a warning under the memory writing needs.
 *  Coulisses downloads nothing itself (P1): it says what to do. */
function WritingAdviceBanner({
  info,
  dev,
  said,
}: {
  info: ModelsInfo;
  dev: boolean;
  said: (name: string) => string;
}) {
  const [copied, setCopied] = useState(false);
  const step = adviceStep(info);
  const short = shortMemory(info);
  const copy = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false); // the command stays shown, to select by hand
    }
  };
  return (
    <>
      {memoryUnknown(info) && (
        <Text type="supporting">
          La mémoire de ce Mac n'a pas pu être lue : aucun modèle ne peut lui être
          conseillé.
        </Text>
      )}
      {short !== null && (
        <Banner
          status="warning"
          title={`Ce Mac a ${short} Go de mémoire`}
          description={`Il en faut au moins ${info.advice.minimum_gb} Go pour rédiger : les titres, les chapitres et les résumés risquent d'échouer faute de mémoire. La transcription, elle, fonctionne.`}
        />
      )}
      {step.kind === "install-ollama" && (
        <Banner
          status="warning"
          title="Ollama ne répond pas"
          description={
            <>
              {dev && info.error ? `${info.error} ` : ""}
              S'il n'est pas installé, téléchargez-le, ouvrez-le, puis revenez
              ici. S'il l'est déjà, lancez l'application Ollama.{" "}
              <a href={OLLAMA_DOWNLOAD} target="_blank" rel="noreferrer">
                Télécharger Ollama
              </a>
            </>
          }
        />
      )}
      {step.kind === "pull" && (
        <Banner
          status="info"
          title={`Modèle conseillé pour ce Mac : ${said(step.model)}`}
          description={
            <>
              Pour l'installer, ouvrez le Terminal et lancez cette commande,
              puis choisissez-le ci-dessous :{" "}
              <code className="cl-code">{step.command}</code>
            </>
          }
          endContent={
            <Button
              label={copied ? "Copié" : "Copier la commande"}
              variant="ghost"
              size="sm"
              onClick={() => void copy(step.command)}
            />
          }
        />
      )}
      {step.kind === "ready" && (
        <Text type="supporting">
          Le modèle conseillé pour ce Mac, {said(step.model)}, est installé.
        </Text>
      )}
      {step.kind === "choose" && (
        <Banner
          status="info"
          title="Aucun modèle de langage n'est installé dans Ollama"
          description={
            <>
              Installez-en un depuis la bibliothèque d'Ollama, puis
              choisissez-le ci-dessous.{" "}
              <a href={OLLAMA_LIBRARY} target="_blank" rel="noreferrer">
                Ouvrir la bibliothèque d'Ollama
              </a>
            </>
          }
        />
      )}
    </>
  );
}

/** The model of a writing: its name, which opens the list of the installed ones, the chosen
 *  one ticked. A model chosen before and since removed from Ollama is said so. */
function ModelPicker({
  label,
  value,
  said,
  dev,
  models,
  reachable,
  onChoose,
}: {
  label: string;
  value: string;
  said: (name: string) => string;
  dev: boolean;
  models: InstalledModel[];
  reachable: boolean;
  onChoose: (model: string) => void;
}) {
  const [isOpen, setOpen] = useState(false);
  const list = useRef<HTMLUListElement>(null);
  const missing = reachable && !models.some((m) => m.name === value);
  // Opened: the focus on the chosen one; ↑ and ↓ go from one to the next.
  useEffect(() => {
    if (!isOpen) return;
    const timer = window.setTimeout(() => {
      const items = [
        ...(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? []),
      ];
      (items.find((b) => b.hasAttribute("aria-current")) ?? items[0])?.focus();
    });
    return () => window.clearTimeout(timer);
  }, [isOpen]);
  const move = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = [
      ...(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? []),
    ];
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    items[
      e.key === "ArrowDown"
        ? Math.min(items.length - 1, at + 1)
        : Math.max(0, at - 1)
    ]?.focus();
  };
  const trigger = (
    <button
      type="button"
      className="cl-modelpick"
      aria-label={`${label} : ${said(value)}. Changer`}
      disabled={!reachable}
    >
      <span className="cl-modelpick__name">{said(value)}</span>
      {missing && (
        <span className="cl-modelpick__missing">absent d'Ollama</span>
      )}
      <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );
  if (!reachable) return trigger;
  return (
    <Popover
      isOpen={isOpen}
      onOpenChange={setOpen}
      label={label}
      placement="below"
      alignment="end"
      width={320}
      padding={1}
      hasAutoFocus={false}
      content={
        <ul
          ref={list}
          className="cl-spacepick"
          aria-label={label}
          onKeyDown={move}
        >
          {models.map((m) => (
            <li key={m.name}>
              <button
                type="button"
                className="cl-spacepick__item"
                aria-current={m.name === value || undefined}
                onClick={() => {
                  setOpen(false);
                  if (m.name !== value) onChoose(m.name);
                }}
              >
                <span className="cl-modelpick__option">
                  <span>{said(m.name)}</span>
                  <span className="cl-modelpick__about">{about(m, dev)}</span>
                </span>
                {m.name === value && (
                  <Check size={16} strokeWidth={1.75} aria-hidden />
                )}
              </button>
            </li>
          ))}
          {models.length === 0 && (
            <li className="cl-nameedit__empty">
              Aucun modèle n'est installé dans Ollama.
            </li>
          )}
        </ul>
      }
    >
      {trigger}
    </Popover>
  );
}

function WritingSkeleton() {
  return (
    <div
      className="cl-writings cl-skeleton"
      aria-busy="true"
      aria-label="Lecture des modèles"
    >
      {[0.3, 0.36, 0.32].map((w, i) => (
        <div key={i} className="cl-writings__row">
          <span className="cl-writings__what">
            <Skeleton width={`${w * 100}%`} height={14} radius={1} index={i} />
            <Skeleton width="60%" height={11} radius={1} index={i} />
          </span>
          <Skeleton width={200} height={32} radius={2} index={i} />
        </div>
      ))}
    </div>
  );
}
