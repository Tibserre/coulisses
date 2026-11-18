import { useState, type ReactNode } from "react";
import { Popover } from "@astryxdesign/core/Popover";
import { Check, ChevronDown, Folder, Languages as LanguageIcon } from "lucide-react";
import {
  api,
  type Language,
  type Project,
  type Session,
  type Space,
} from "../api.ts";
import { inLanguage, languageWorthShowing } from "../languages.ts";
import { LanguageDownloadDialog, LanguagePick, useLanguages } from "./Languages.tsx";

/** Where a recording goes, changed while it runs (spec §7.2, ADR 0056, D5a): its language
 *  (ADR 0072), when it has something to say, then its space and project, in one list (the
 *  space, its projects under it). A recording starts in one gesture, in the space selected;
 *  this is where it is put right. Each one is a quiet label that opens its list, floating
 *  under it: nothing moves. The processing starts at the stop, in the language of the
 *  moment. Who is there is said apart (« Qui est là ? »). */
export function RecordingContext({
  session,
  spaces,
  projects,
  onChanged,
  onError,
}: {
  session: Session;
  spaces: Space[];
  projects: Project[];
  onChanged: (session: Session) => void;
  onError: (message: string) => void;
}) {
  /** People unchecked by a move to another space: said, never silent (P8). */
  const [unchecked, setUnchecked] = useState<string[]>([]);

  const { languages, reload } = useLanguages(onError);
  const [toDownload, setToDownload] = useState<Language | null>(null);

  /** Done (true), or refused and said. */
  const run = async (step: () => Promise<Session>) => {
    try {
      onChanged(await step());
      return true;
    } catch (e) {
      onError((e as Error).message);
      return false;
    }
  };

  const space = spaces.find((s) => s.id === session.space_id);
  const project = projects.find((p) => p.id === session.project_id);

  /** Into a space (and one of its projects, or none): moved first if it is another. */
  const place = (spaceId: number, projectId: number | null) =>
    void (async () => {
      try {
        let next = session;
        if (spaceId !== session.space_id) {
          const moved = await api.moveSession(session.id, spaceId);
          // Said once done, by the service: who was unchecked, archived ones too.
          setUnchecked(moved.unchecked);
          next = moved.session;
          // Shown at once: if the project then fails, the space shown is the true one.
          onChanged(next);
        }
        if (projectId !== next.project_id)
          next = await api.setSessionProject(session.id, projectId);
        onChanged(next);
      } catch (e) {
        onError((e as Error).message);
      }
    })();

  return (
    <div className="cl-rec__context">
      {languages && languageWorthShowing(languages, session.language) && (
        <LanguagePick
          languages={languages}
          value={session.language}
          title="Langue de la séance"
          intro="Le traitement partira à l'arrêt, dans cette langue."
          onPick={(l) =>
            void run(() => api.setSessionLanguage(session.id, l.language)).then((done) => {
              if (done && !l.installed) setToDownload(l);
            })
          }
        >
          <button
            type="button"
            className="cl-chip cl-chip--quiet"
            aria-label={`Langue de la séance : ${inLanguage(languages, session.language)}. Changer`}
          >
            <LanguageIcon size={16} strokeWidth={1.75} aria-hidden />
            {inLanguage(languages, session.language)}
            <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
          </button>
        </LanguagePick>
      )}
      {languages && languageWorthShowing(languages, session.language) && (
        <span className="cl-rec__mid" aria-hidden>
          ·
        </span>
      )}
      <ChipMenu
        label={project ? `${space?.name ?? "Espace"} / ${project.name}` : (space?.name ?? "Espace")}
        title="Espace et projet"
        icon={<Folder size={16} strokeWidth={1.75} aria-hidden />}
      >
        {(close) =>
          spaces
            .filter((s) => !s.archived)
            .flatMap((s) => [
              <Choice
                key={`e${s.id}`}
                isCurrent={s.id === session.space_id && session.project_id === null}
                onPick={() => {
                  close();
                  place(s.id, null);
                }}
              >
                {s.name}
              </Choice>,
              ...projects
                .filter((p) => p.space_id === s.id && !p.archived)
                .map((p) => (
                  <Choice
                    key={`p${p.id}`}
                    isCurrent={p.id === session.project_id}
                    indent
                    onPick={() => {
                      close();
                      place(s.id, p.id);
                    }}
                  >
                    {p.name}
                  </Choice>
                )),
            ])
        }
      </ChipMenu>
      <LanguageDownloadDialog
        language={toDownload}
        after="Le traitement partira à l'arrêt, dès que le modèle sera là."
        onClose={() => setToDownload(null)}
        onStarted={() => void reload()}
      />
      {unchecked.length > 0 && (
        <span className="cl-rec__said" role="status">
          Décochés en changeant d'espace : {unchecked.join(", ")}.
        </span>
      )}
    </div>
  );
}

/** A quiet label that opens its list below it, floating (no native select). */
function ChipMenu({
  label,
  title,
  icon,
  children,
}: {
  label: string;
  title: string;
  icon: ReactNode;
  children: (close: () => void) => ReactNode[];
}) {
  const [isOpen, setOpen] = useState(false);
  return (
    <Popover
      isOpen={isOpen}
      onOpenChange={setOpen}
      label={title}
      placement="below"
      alignment="start"
      width={260}
      padding={1}
      content={
        <ul className="cl-spacepick" aria-label={title}>
          {children(() => setOpen(false))}
        </ul>
      }
    >
      <button
        type="button"
        className="cl-chip cl-chip--quiet"
        aria-label={`${title} : ${label}. Changer`}
      >
        {icon}
        {label}
        <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
      </button>
    </Popover>
  );
}

function Choice({
  isCurrent,
  onPick,
  indent = false,
  children,
}: {
  isCurrent: boolean;
  onPick: () => void;
  /** A project, under its space. */
  indent?: boolean;
  children: ReactNode;
}) {
  return (
    <li>
      <button
        type="button"
        className="cl-spacepick__item"
        data-indent={indent || undefined}
        aria-current={isCurrent || undefined}
        onClick={onPick}
      >
        <span>{children}</span>
        {isCurrent && <Check size={16} strokeWidth={1.75} aria-hidden />}
      </button>
    </li>
  );
}
