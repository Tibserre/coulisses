import { useCallback, useEffect, useMemo, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import {
  MetadataList,
  MetadataListItem,
} from "@astryxdesign/core/MetadataList";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { ArrowLeft } from "lucide-react";
import {
  api,
  type AttributedTranscript,
  type SessionDetail,
  type StageView,
} from "../api.ts";
import { PlayerBar } from "../components/PlayerBar.tsx";
import { ProvenanceDialog } from "../components/ProvenanceDialog.tsx";
import { StageList } from "../components/StageList.tsx";
import { TranscriptView } from "../components/TranscriptView.tsx";
import { formatBytes, formatDate, formatDuration, plural } from "../format.ts";
import { buildModel, turnAt, wordAt, type ReviewModel } from "../transcript.ts";
import { usePlayback } from "../usePlayback.ts";

export function SessionPage({ id }: { id: string }) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [transcript, setTranscript] = useState<AttributedTranscript | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [provenanceOf, setProvenanceOf] = useState<StageView | null>(null);
  const pb = usePlayback();

  const refresh = useCallback(async () => {
    try {
      setDetail(await api.session(id));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  const jobState = detail?.session.job_state;
  const attribute = detail?.stages.find((s) => s.stage === "attribute");
  const attributeRun =
    attribute?.state === "succeeded" ? attribute.run_id : null;

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Follow the processing while it runs; nothing to poll once it is over.
  useEffect(() => {
    if (jobState !== "queued" && jobState !== "running") return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [jobState, refresh]);

  useEffect(() => {
    if (!attributeRun) return;
    api.transcript(id).then(
      (t) => {
        setTranscript(t);
        setTranscriptError(null);
      },
      (e: Error) => setTranscriptError(e.message),
    );
  }, [id, attributeRun]);

  const model = useMemo(
    () => (transcript ? buildModel(transcript) : null),
    [transcript],
  );
  const currentRow = model ? turnAt(model, pb.time) : null;
  const current = currentRow
    ? { row: currentRow, word: wordAt(currentRow, pb.time) }
    : null;

  const session = detail?.session;
  const title = session
    ? (session.title ??
      `Séance du ${formatDate(session.recorded_at).toLowerCase()}`)
    : "";

  return (
    <div className="cl-review">
      <audio ref={pb.audioRef} src={api.audioUrl(id)} preload="metadata" />
      <header className="cl-review__header">
        <a className="cl-back" href="#/">
          <ArrowLeft size={16} strokeWidth={1.75} aria-hidden /> Enregistrements
        </a>
        {session && (
          <div>
            <Text type="supporting">
              {detail?.source?.origin === "captured"
                ? "Enregistrement capté"
                : "Enregistrement importé"}
            </Text>
            <Heading level={1}>{title}</Heading>
            <Text color="secondary">
              {formatDate(session.recorded_at)} ·{" "}
              {formatDuration(session.duration_s)}
              {session.attendee_count
                ? ` · ${plural(session.attendee_count, "présent", "présents")}`
                : ""}
            </Text>
          </div>
        )}
      </header>

      {error && (
        <div className="cl-review__notice">
          <Banner status="error" title="Séance illisible" description={error} />
        </div>
      )}
      {detail && !model && (
        <ProcessingPanel
          detail={detail}
          transcriptError={transcriptError}
          onResume={async () => {
            await api.resume(id);
            await refresh();
          }}
          onShowProvenance={setProvenanceOf}
        />
      )}
      {detail && model && (
        <>
          <div className="cl-review__columns">
            <TranscriptView model={model} pb={pb} current={current} />
            <aside className="cl-side">
              <KeyFigures
                model={model}
                duration={session?.duration_s ?? null}
              />
              <Participants model={model} />
              <section>
                <Heading level={3}>Traitement</Heading>
                <StageList
                  stages={detail.stages}
                  onShowProvenance={setProvenanceOf}
                />
              </section>
              <SourceInfo detail={detail} />
            </aside>
          </div>
          <PlayerBar model={model} pb={pb} current={currentRow} />
        </>
      )}
      <ProvenanceDialog
        sessionId={id}
        stage={provenanceOf}
        onClose={() => setProvenanceOf(null)}
      />
    </div>
  );
}

function ProcessingPanel({
  detail,
  transcriptError,
  onResume,
  onShowProvenance,
}: {
  detail: SessionDetail;
  transcriptError: string | null;
  onResume: () => Promise<void>;
  onShowProvenance: (s: StageView) => void;
}) {
  const { session } = detail;
  const failed = session.job_state === "failed";
  const running = session.job_state === "queued" || session.job_state === "running";
  const attributed = detail.stages.some((s) => s.stage === "attribute" && s.state === "succeeded");
  const [resumeError, setResumeError] = useState<string | null>(null);
  const resume = async () => {
    setResumeError(null);
    try {
      await onResume();
    } catch (e) {
      setResumeError((e as Error).message);
    }
  };
  return (
    <main className="cl-processing">
      <Heading level={2}>
        {failed
          ? "Le traitement s'est arrêté"
          : session.job_state === "done"
            ? "Traitement terminé"
            : running
              ? "Traitement en cours"
              : "Jamais traitée"}
      </Heading>
      {session.job_state === null && (
        <Banner
          status="warning"
          title="Aucun traitement n'a été demandé pour cet enregistrement"
          description="Cela ne devrait pas arriver après un import : signalez-le."
        />
      )}
      {running && (
        <Text color="secondary">
          Environ 10 minutes de calcul par heure d'audio. Vous pouvez fermer
          cette page : le traitement continue tant que Coulisses tourne, et
          reprend où il en était s'il est interrompu.
        </Text>
      )}
      {session.job_state === "queued" && (
        <Text color="secondary">
          En file : un autre enregistrement est peut-être en cours de
          traitement.
        </Text>
      )}
      {failed && (
        <Banner
          status="error"
          title="Une étape a échoué"
          description={`${session.job_error ?? "Erreur inconnue"}. Les étapes réussies sont gardées ; reprendre ne relance que le reste.`}
          endContent={
            <Button
              label="Reprendre le traitement"
              variant="primary"
              size="sm"
              clickAction={resume}
            />
          }
        />
      )}
      {resumeError && (
        <Banner status="error" title="La reprise a échoué" description={resumeError} />
      )}
      {detail.source && !detail.source.file_present && (
        <Banner
          status="error"
          title="Enregistrement introuvable"
          description={`Le fichier ${detail.source.file_name} n'est plus dans le dossier de la séance. A-t-il été déplacé ou supprimé dans le Finder ?`}
        />
      )}
      {transcriptError && (
        <Banner
          status="error"
          title="Transcript illisible"
          description={transcriptError}
        />
      )}
      <StageList stages={detail.stages} onShowProvenance={onShowProvenance} />
      {session.job_state === "done" && attributed && !transcriptError && (
        <Spinner label="Chargement du transcript" />
      )}
      {session.job_state === "done" && !attributed && (
        <Banner
          status="error"
          title="Traitement terminé, mais le transcript est absent"
          description="L'étape « Qui a dit quoi » n'a pas de résultat réussi. Consultez les étapes ci-dessus."
        />
      )}
    </main>
  );
}

function KeyFigures({
  model,
  duration,
}: {
  model: ReviewModel;
  duration: number | null;
}) {
  const voices = model.speakers.filter((s) => s.label !== null).length;
  return (
    <dl className="cl-figures">
      <div>
        <dt>Durée</dt>
        <dd>{formatDuration(duration)}</dd>
      </div>
      <div>
        <dt>Voix</dt>
        <dd>{voices}</dd>
      </div>
      <div>
        <dt>Répliques</dt>
        <dd>
          {model.rows.filter((r) => r.kind === "turn").length}
        </dd>
      </div>
      <div>
        <dt>Mots horodatés</dt>
        <dd>{Math.round(model.timedShare * 100)} %</dd>
      </div>
    </dl>
  );
}

function Participants({ model }: { model: ReviewModel }) {
  const total = model.speakers.reduce((sum, s) => sum + s.seconds, 0) || 1;
  return (
    <section>
      <Heading level={3}>Participants</Heading>
      <Text type="supporting">
        Les voix trouvées, numérotées dans l'ordre où elles prennent la parole.
      </Text>
      <ul className="cl-participants">
        {model.speakers.map((s) => (
          <li key={s.label ?? "inconnu"}>
            <span className="cl-name" data-unnamed>
              {s.name}
            </span>
            <span className="cl-share" aria-hidden>
              <span style={{ width: `${(100 * s.seconds) / total}%` }} />
            </span>
            <Text type="supporting">
              {Math.round((100 * s.seconds) / total)} %
            </Text>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SourceInfo({ detail }: { detail: SessionDetail }) {
  const source = detail.source;
  if (!source) return null;
  return (
    <section>
      <Heading level={3}>Enregistrement</Heading>
      <MetadataList label={{ position: "start", width: 110 }}>
        <MetadataListItem label="Fichier d'origine">
          {source.original_name}
        </MetadataListItem>
        <MetadataListItem label="Taille">
          {formatBytes(source.size_bytes)}
        </MetadataListItem>
        <MetadataListItem label="Format">
          {[
            source.codec,
            source.sample_rate ? `${source.sample_rate / 1000} kHz` : null,
            source.channels ? plural(source.channels, "canal", "canaux") : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </MetadataListItem>
        <MetadataListItem label="Empreinte">
          <code className="cl-code" title={source.sha256}>
            {source.sha256.slice(0, 16)}…
          </code>
        </MetadataListItem>
      </MetadataList>
    </section>
  );
}
