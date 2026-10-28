import { useEffect, useState } from "react";
import { Popover } from "@astryxdesign/core/Popover";
import {
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  Mic,
  MicOff,
  Plus,
  Smartphone,
  TriangleAlert,
  X,
} from "lucide-react";
import { api, type InputDevice, type RecordingState } from "../api.ts";
import { LevelMeter } from "./LevelMeter.tsx";
import { meterValue } from "../meter.ts";
import {
  addable,
  barLevel,
  isPhone,
  micSummary,
  type Mic as MicTrack,
} from "../microphones.ts";

/** The microphones in the recording bar (ADR 0067), as the computer's sound: their icon
 *  and level are one button, which cuts or brings back every microphone (the icon then
 *  crossed); beside it, the chevron opens their list under the whole button (each cut on
 *  its own, one added taken away, one added), or « + » adds a second one when there is
 *  only one. A click shows at once: a cut before the service answers (taken back if it
 *  refuses), a microphone being opened or taken away says so. */
export function MicsControl({
  mics: heard,
  act,
}: {
  mics: MicTrack[];
  /** Asks the service, shows the state it answers, says its error. */
  act: (step: () => Promise<RecordingState>) => Promise<boolean>;
}) {
  const [isOpen, setOpen] = useState(false);
  const [adding, setAdding] = useState<InputDevice[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  /** Cuts asked and not answered yet: shown at once. */
  const [asked, setAsked] = useState<Record<string, boolean>>({});
  /** The microphone being opened (its index). */
  const [opening, setOpening] = useState<number | null>(null);
  /** The microphone being taken away (its source). */
  const [removing, setRemoving] = useState<string | null>(null);
  /** The one just added: it comes in. */
  const [fresh, setFresh] = useState<string | null>(null);
  useEffect(() => {
    if (!fresh) return;
    const timer = window.setTimeout(() => setFresh(null), 1000);
    return () => window.clearTimeout(timer);
  }, [fresh]);

  const mics = heard.map((m) =>
    m.sourceId in asked ? { ...m, muted: asked[m.sourceId] } : m,
  );
  const summary = micSummary(mics);
  const level = barLevel(mics);
  // One microphone only: « + » opens straight on those one can add.
  const single = mics.length === 1;
  const all = summary.allCut
    ? "Rétablir tous les micros"
    : "Couper tous les micros";

  const showAddable = async () => {
    // The adding view at once, empty while the Mac lists its microphones.
    setLoading(true);
    setAdding((now) => now ?? []);
    try {
      setAdding(addable(await api.microphones(), mics));
      setProblem(null);
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  const open = (next: boolean) => {
    setOpen(next);
    if (next && single) void showAddable();
    if (!next) {
      setAdding(null);
      setProblem(null);
    }
  };
  /** A cut shown at once; the service's state is shown again once it answers (a refusal
   *  is said by the page). A second click while one is asked waits for it. */
  const cut = async (
    ids: string[],
    muted: boolean,
    step: () => Promise<RecordingState>,
  ) => {
    if (ids.some((id) => id in asked)) return;
    setAsked((now) => ({
      ...now,
      ...Object.fromEntries(ids.map((id) => [id, muted])),
    }));
    await act(step);
    setAsked((now) =>
      Object.fromEntries(
        Object.entries(now).filter(([id]) => !ids.includes(id)),
      ),
    );
  };
  const cutAll = () =>
    cut(
      mics.map((m) => m.sourceId),
      !summary.allCut,
      () => api.muteMicrophones(!summary.allCut),
    );
  // A refusal (not here any more, already there) is said by the page; the list stays.
  const add = async (device: InputDevice) => {
    const before = new Set(heard.map((m) => m.sourceId));
    setOpening(device.index);
    let added: string | null = null;
    const done = await act(async () => {
      const next = await api.addMicrophone(device.index);
      added =
        next.extra.find((t) => !before.has(t.source_id))?.source_id ?? null;
      return next;
    });
    setOpening(null);
    if (done) {
      setAdding(null);
      setFresh(added);
    }
  };

  // Taken away: its file ends there and stays with the session; a refusal is said.
  const remove = async (m: MicTrack) => {
    setRemoving(m.sourceId);
    await act(() => api.removeMicrophone(m.sourceId));
    setRemoving(null);
  };

  const list = adding ? (
    <div className="cl-mics__pop">
      <div className="cl-mics__head">
        <button
          type="button"
          className="cl-mics__icon"
          aria-label="Revenir aux micros"
          onClick={() => {
            setAdding(null);
            setProblem(null);
          }}
        >
          <ChevronLeft size={14} strokeWidth={1.75} aria-hidden />
        </button>
        Ajouter un micro
      </div>
      {adding.length === 0 && !loading && !problem && (
        <p className="cl-mics__foot">
          Aucun autre micro sur ce Mac. Un iPhone apparaît s'il est près du Mac,
          avec Continuité.
        </p>
      )}
      <ul className="cl-mics__list">
        {adding.map((d) => (
          <li key={d.index}>
            <button
              type="button"
              className="cl-mics__pick"
              data-busy={opening === d.index || undefined}
              disabled={opening !== null}
              onClick={() => void add(d)}
            >
              {isPhone(d.name) ? (
                <Smartphone size={16} strokeWidth={1.75} aria-hidden />
              ) : (
                <Mic size={16} strokeWidth={1.75} aria-hidden />
              )}
              <span className="cl-mics__name">{d.name}</span>
              {opening === d.index && (
                <span className="cl-mics__busy" role="status">
                  Connexion…
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {problem && <p className="cl-mics__problem">{problem}</p>}
      {adding.length > 0 && !loading && (
        <p className="cl-mics__foot">Il enregistre à partir de maintenant.</p>
      )}
    </div>
  ) : (
    <div className="cl-mics__pop">
      <ul className="cl-mics__list">
        {mics.map((m) => (
          <li
            key={m.sourceId}
            className="cl-mics__row"
            data-muted={m.muted || undefined}
            data-fresh={fresh === m.sourceId || undefined}
            data-busy={removing === m.sourceId || undefined}
          >
            {/* As the bar's button: its icon and level cut it or bring it back, the icon
                then crossed and the level flat. */}
            <button
              type="button"
              className="cl-mics__src"
              data-muted={m.muted || undefined}
              title={m.muted ? `Rétablir ${m.device}` : `Couper ${m.device}`}
              aria-label={
                m.muted
                  ? `${m.device} coupé. Le rétablir`
                  : `${m.device}${m.lost ? ", plus rien n'arrive" : ""}. Le couper`
              }
              disabled={removing === m.sourceId}
              onClick={(e) => {
                e.currentTarget.blur();
                void cut([m.sourceId], !m.muted, () =>
                  api.muteTrack(m.sourceId, !m.muted),
                );
              }}
            >
              {m.muted ? (
                <MicOff size={16} strokeWidth={1.75} aria-hidden />
              ) : m.lost ? (
                <TriangleAlert
                  className="cl-mics__lost"
                  size={16}
                  strokeWidth={1.75}
                  aria-hidden
                />
              ) : isPhone(m.device) ? (
                <Smartphone size={16} strokeWidth={1.75} aria-hidden />
              ) : (
                <Mic size={16} strokeWidth={1.75} aria-hidden />
              )}
              <span className="cl-mics__name">
                {m.device}
                {removing === m.sourceId && (
                  <span role="status"> · retrait…</span>
                )}
              </span>
              <span className="cl-mics__meter">
                <LevelMeter
                  level={m.muted ? 0 : meterValue(m.rms_db)}
                  peak={m.muted ? 0 : meterValue(m.peak_db)}
                  clipping={!m.muted && m.clipping}
                />
              </span>
            </button>
            {/* The main microphone stays: the processing listens to it. */}
            {m.sourceId !== mics[0]?.sourceId && (
              <button
                type="button"
                className="cl-mics__icon"
                title={`Retirer ${m.device} (ce qu'il a enregistré est gardé)`}
                aria-label={`Retirer ${m.device}`}
                disabled={removing !== null}
                onClick={() => void remove(m)}
              >
                <X size={15} strokeWidth={1.75} aria-hidden />
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="cl-mics__rule" />
      <button
        type="button"
        className="cl-mics__action"
        data-kind="add"
        onClick={() => void showAddable()}
      >
        <Plus size={15} strokeWidth={1.75} aria-hidden />
        Ajouter un micro
      </button>
      <button
        type="button"
        className="cl-mics__action"
        onClick={() => void cutAll()}
      >
        {summary.allCut ? (
          <Mic size={15} strokeWidth={1.75} aria-hidden />
        ) : (
          <MicOff size={15} strokeWidth={1.75} aria-hidden />
        )}
        {all}
      </button>
      {problem && <p className="cl-mics__problem">{problem}</p>}
    </div>
  );

  return (
    <Popover
      isOpen={isOpen}
      onOpenChange={open}
      label="Les micros"
      placement="below"
      alignment="start"
      width={312}
      padding={1}
      content={list}
    >
      {(trigger) => (
        // The list opens under the whole button; only the chevron opens it.
        <span className="cl-mics" ref={trigger.ref}>
          <button
            type="button"
            className="cl-mics__all"
            data-muted={summary.allCut || undefined}
            title={all}
            aria-label={`${summary.count === 1 ? "Micro" : `${summary.count} micros`}${
              summary.cut && !summary.allCut
                ? `, dont ${summary.cut} coupé${summary.cut > 1 ? "s" : ""}`
                : ""
            }${summary.lost ? ", l'un ne répond plus" : ""}. ${all}`}
            onClick={(e) => {
              e.currentTarget.blur();
              void cutAll();
            }}
          >
            {summary.allCut ? (
              <MicOff size={18} strokeWidth={1.75} aria-hidden />
            ) : (
              <Mic size={18} strokeWidth={1.75} aria-hidden />
            )}
            {summary.count > 1 && (
              <span className="cl-mics__count">{summary.count}</span>
            )}
            {summary.lost && (
              <TriangleAlert
                className="cl-mics__lost"
                size={13}
                strokeWidth={1.75}
                aria-hidden
              />
            )}
            <span className="cl-mics__meter">
              <LevelMeter
                level={summary.allCut ? 0 : meterValue(level.rms_db)}
                peak={summary.allCut ? 0 : meterValue(level.peak_db)}
                clipping={mics.some((m) => !m.muted && m.clipping)}
              />
            </span>
          </button>
          <button
            type="button"
            className="cl-mics__more"
            data-open={isOpen || undefined}
            aria-haspopup={trigger["aria-haspopup"]}
            aria-expanded={trigger["aria-expanded"]}
            aria-controls={trigger["aria-controls"]}
            title={single ? "Ajouter un micro" : "Les micros"}
            aria-label={single ? "Ajouter un micro" : "Les micros"}
            onClick={(e) => trigger.onClick(e)}
          >
            {single ? (
              <Plus size={14} strokeWidth={1.75} aria-hidden />
            ) : isOpen ? (
              <ChevronUp size={14} strokeWidth={1.75} aria-hidden />
            ) : (
              <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
            )}
          </button>
        </span>
      )}
    </Popover>
  );
}
