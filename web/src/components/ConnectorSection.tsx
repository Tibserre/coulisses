import { useCallback, useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import { api, type ConnectorAccess, type ConnectorSettings } from "../api.ts";
import {
  accessSubject,
  connectorReach,
  spaceReading,
  TOOL_LABEL,
} from "../connector.ts";
import { useDevMode } from "../devMode.ts";
import { sessionHref } from "../library.ts";
import { formatDateTime } from "../format.ts";

/** The « Connecteur » tab of the Settings (ADR 0065, spec §7.13): an assistant reads
 *  Coulisses, never drives it. Closed by default; what opening it implies is said before the
 *  switch. The spaces it reads are chosen in each space's settings, summed up here. Then how
 *  to plug an assistant in, and every read it made, never purged. */
export function ConnectorSection({
  onError,
}: {
  onError: (message: string | null) => void;
}) {
  const dev = useDevMode();
  const [settings, setSettings] = useState<ConnectorSettings | null>(null);
  const [entries, setEntries] = useState<ConnectorAccess[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  // The copy refused (no clipboard): the command is shown, to select by hand.
  const [copyFailed, setCopyFailed] = useState(false);

  // Read apart: one refused, the other still shows.
  const load = useCallback(() => {
    api.connector().then(setSettings, (e: Error) => onError(e.message));
    api.connectorJournal().then(
      (journal) => {
        setEntries(journal.entries);
        setNext(journal.next);
      },
      (e: Error) => onError(e.message),
    );
  }, [onError]);
  useEffect(load, [load]);

  const act = async (what: () => Promise<void>) => {
    try {
      await what();
      onError(null);
    } catch (e) {
      onError((e as Error).message);
    }
  };
  const copy = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setCopyFailed(false);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
      setCopyFailed(true);
    }
  };

  const reach = settings ? connectorReach(settings) : null;
  return (
    <>
      <section className="cl-settings__section">
        <Heading level={3}>Connecteur des assistants</Heading>
        <Text color="secondary">
          Un assistant (Claude Desktop, Claude Code, ou un assistant local) peut
          lire vos séances : chercher, lire une séance, un résumé, le transcript
          corrigé. Il ne peut rien enregistrer, importer, rédiger ni corriger,
          et n'a accès ni à l'audio ni aux réglages.
        </Text>
        <div className="cl-connector__warning">
          <Text>
            Un assistant distant envoie ce qu'il lit à son fournisseur.
          </Text>
          <ul className="cl-list">
            <li>
              <Text color="secondary">
                Ce qui est lu y part et y reste, même si vous supprimez la
                séance dans Coulisses.
              </Text>
            </li>
            <li>
              <Text color="secondary">
                Ce sont aussi les paroles des autres participants : c'est à vous
                de juger si vous pouvez les transmettre.
              </Text>
            </li>
            <li>
              <Text color="secondary">
                Un transcript peut contenir des consignes adressées à
                l'assistant, dites par quelqu'un pendant la séance.
              </Text>
            </li>
            <li>
              <Text color="secondary">
                Un assistant peut ouvrir Coulisses en arrière-plan pour le lire.
              </Text>
            </li>
          </ul>
        </div>
        {settings === null ? (
          <Skeleton width={240} height={20} radius={1} />
        ) : (
          <Switch
            label="Ouvrir le connecteur"
            description={
              settings.open
                ? "Ouvert : un assistant branché peut lire les espaces qui lui sont accessibles."
                : "Coupé : toute lecture est refusée."
            }
            value={settings.open}
            onChange={(open) =>
              void act(async () =>
                setSettings(await api.setConnectorOpen(open)),
              )
            }
          />
        )}
        {reach === "no-space" && (
          <Banner
            status="info"
            title="Aucun espace n'est accessible"
            description="Le connecteur est ouvert, mais il ne lit rien : rendez un espace accessible dans ses paramètres."
          />
        )}
      </section>

      <section className="cl-settings__section">
        <Heading level={3}>Espaces lus</Heading>
        <Text color="secondary">
          Chaque espace est fermé au connecteur tant que vous ne l'ouvrez pas
          dans ses paramètres. Sans « Transmettre les noms », chaque nom connu
          de l'espace devient « Personne A », « Personne B »…
        </Text>
        {settings === null ? (
          <Skeleton width={200} height={14} radius={1} />
        ) : settings.spaces.length === 0 ? (
          <Text color="secondary">Aucun espace.</Text>
        ) : (
          <ul className="cl-settings__list">
            {settings.spaces.map((s) => (
              <li key={s.id}>
                <span className="cl-settings__text">
                  <a href={`#/espaces/${s.id}`}>{s.name}</a>
                </span>
                <Text color="secondary">{spaceReading(s)}</Text>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="cl-settings__section">
        <Heading level={3}>Brancher un assistant</Heading>
        <Text color="secondary">
          Coulisses n'écrit jamais dans la configuration d'un autre outil :
          c'est vous qui branchez l'assistant, et il vous demande votre accord à
          chaque lecture.
        </Text>
        {settings && !settings.launcher_ready && (
          <Banner
            status="warning"
            title="Le connecteur n'a pas pu être préparé"
            description="Coulisses n'a pas pu préparer le programme que lancent les assistants : on ne peut pas en brancher un pour l'instant. Le détail est dans le journal technique (Réglages › Avancé)."
          />
        )}
        {settings && (
          <ul className="cl-settings__list">
            <li>
              <span className="cl-settings__text">
                <Text>Claude Code</Text>
                <Text type="supporting">
                  Une ligne à coller dans le Terminal, une fois.
                </Text>
                {copyFailed && (
                  <Text type="supporting">
                    La copie n'a pas marché : sélectionnez la ligne à la main.
                  </Text>
                )}
                {(dev || copyFailed) && (
                  <Text type="supporting">
                    <code className="cl-code">{settings.claude_code_command}</code>
                  </Text>
                )}
              </span>
              <Button
                size="sm"
                variant="ghost"
                label={copied ? "Copié" : "Copier la commande"}
                isDisabled={!settings.launcher_ready}
                onClick={() => void copy(settings.claude_code_command)}
              />
            </li>
            <li>
              <span className="cl-settings__text">
                <Text>Claude Desktop</Text>
                <Text type="supporting">
                  {settings.mcpb
                    ? "L'extension s'ouvre dans Claude Desktop, qui demande de l'installer."
                    : "L'extension pour Claude Desktop n'est pas encore là."}
                </Text>
              </span>
              {settings.mcpb && (
                <Button
                  size="sm"
                  label="Ouvrir l'extension"
                  isDisabled={!settings.launcher_ready}
                  clickAction={() => act(() => api.openConnectorExtension())}
                />
              )}
            </li>
          </ul>
        )}
        {dev && settings && (
          <Text type="supporting">
            Lanceur : {settings.launcher}
            {settings.mcpb ? ` · extension : ${settings.mcpb}` : ""}
          </Text>
        )}
      </section>

      <section className="cl-settings__section">
        <Heading level={3}>Journal des accès</Heading>
        <Text color="secondary">
          Chaque lecture d'un assistant, la plus récente d'abord, jamais
          effacée. Ce qu'il a cherché n'y est pas noté.
        </Text>
        {entries === null ? (
          <Skeleton width={260} height={14} radius={1} />
        ) : entries.length === 0 ? (
          <Text color="secondary">Aucune lecture pour l'instant.</Text>
        ) : (
          <ul className="cl-settings__list">
            {entries.map((e) => {
              const subject = accessSubject(e);
              return (
                <li key={e.id}>
                  <span className="cl-settings__text">
                    <Text>
                      {TOOL_LABEL[e.tool]}
                      {subject === null ? (
                        e.tool === "chercher" || e.tool === "lister_seances" ? (
                          " : aucune séance rendue"
                        ) : null
                      ) : e.session_deleted || e.session_id === null ? (
                        ` : ${subject}`
                      ) : (
                        <>
                          {" : "}
                          <a
                            href={sessionHref(e.session_id)}
                          >
                            {subject}
                          </a>
                        </>
                      )}
                    </Text>
                    <Text type="supporting">
                      {formatDateTime(e.at)} ·{" "}
                      {e.names_shared ? "avec les noms" : "noms masqués"}
                    </Text>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        {next !== null && (
          <div>
            <Button
              size="sm"
              variant="ghost"
              label="Voir les plus anciennes"
              clickAction={() =>
                act(async () => {
                  const older = await api.connectorJournal(next);
                  setEntries((was) => [...(was ?? []), ...older.entries]);
                  setNext(older.next);
                })
              }
            />
          </div>
        )}
      </section>
    </>
  );
}
