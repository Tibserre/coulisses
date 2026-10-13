import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Banner } from "@astryxdesign/core/Banner";
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

/** A model as the lists say it: its size in parameters and on the disk. */
function about(m: InstalledModel): string {
  return [m.parameter_size, formatBytes(m.size_bytes)]
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

  const used = (name: string) =>
    WRITINGS.filter((w) => info?.writings[w.writing] === name).map((w) => w.label);

  return (
    <>
      <section className="cl-settings__section">
        <Heading level={3}>Modèles de rédaction</Heading>
        <Text color="secondary">
          Les titres, les chapitres et les résumés sont rédigés par un modèle de
          langage qui tourne sur ce Mac, dans Ollama. Un changement vaut pour ce
          qui est demandé ensuite ; ce qui est déjà rédigé garde son modèle.
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
        {info && !info.reachable && (
          <Banner
            status="warning"
            title="Ollama ne répond pas"
            description={`${dev && info.error ? `${info.error} ` : ""}Lancez l'application Ollama pour voir les modèles installés et rédiger.`}
          />
        )}
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

      {info?.reachable && (
        <section className="cl-settings__section">
          <Heading level={3}>Installés dans Ollama</Heading>
          {info.models.length === 0 ? (
            <Text color="secondary">
              Aucun modèle n'est installé dans Ollama.
            </Text>
          ) : (
            <ul className="cl-settings__list">
              {info.models.map((m) => {
                const uses = used(m.name);
                return (
                  <li key={m.name}>
                    <span className="cl-settings__text">
                      <Text>{m.name}</Text>
                      <Text type="supporting">
                        {about(m)}
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

/** The model of a writing: its name, which opens the list of the installed ones, the chosen
 *  one ticked. A model chosen before and since removed from Ollama is said so. */
function ModelPicker({
  label,
  value,
  models,
  reachable,
  onChoose,
}: {
  label: string;
  value: string;
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
      aria-label={`${label} : ${value}. Changer`}
      disabled={!reachable}
    >
      <span className="cl-modelpick__name">{value}</span>
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
                  <span>{m.name}</span>
                  <span className="cl-modelpick__about">{about(m)}</span>
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
