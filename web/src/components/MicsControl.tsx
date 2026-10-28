import { useState } from "react";
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

/** The microphones in the recording bar (ADR 0067): one button in two. Its icon cuts or
 *  brings back every microphone at once; the rest opens their list, where each is cut on
 *  its own, and one is added. The computer's sound keeps its own button beside. */
export function MicsControl({
  mics,
  act,
}: {
  mics: MicTrack[];
  /** Asks the service, shows the state it answers, says its error. */
  act: (step: () => Promise<RecordingState>) => Promise<boolean>;
}) {
  const [isOpen, setOpen] = useState(false);
  const [adding, setAdding] = useState<InputDevice[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const summary = micSummary(mics);
  const level = barLevel(mics);
  const open = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setAdding(null);
      setProblem(null);
    }
  };
  const showAddable = async () => {
    try {
      setAdding(addable(await api.microphones(), mics));
      setProblem(null);
    } catch (e) {
      setProblem((e as Error).message);
    }
  };
  // A refusal (not here any more, already there) is said by the page; the list stays.
  const add = async (device: InputDevice) => {
    if (await act(() => api.addMicrophone(device.index))) setAdding(null);
  };
  const all = summary.allCut
    ? "Rétablir tous les micros"
    : "Couper tous les micros";

  return (
    <span className="cl-mics">
      <button
        type="button"
        className="cl-mics__all"
        data-muted={summary.allCut || undefined}
        title={all}
        aria-label={all}
        onClick={(e) => {
          e.currentTarget.blur();
          void act(() => api.muteMicrophones(!summary.allCut));
        }}
      >
        {summary.allCut ? (
          <MicOff size={16} strokeWidth={1.75} aria-hidden />
        ) : (
          <Mic size={16} strokeWidth={1.75} aria-hidden />
        )}
      </button>
      <Popover
        isOpen={isOpen}
        onOpenChange={open}
        label="Les micros"
        placement="below"
        alignment="start"
        width={280}
        padding={1}
        content={
          adding ? (
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
              {adding.length === 0 && (
                <p className="cl-mics__foot">
                  Aucun autre micro sur ce Mac. Un iPhone apparaît s'il est près
                  du Mac, avec Continuité.
                </p>
              )}
              <ul className="cl-mics__list">
                {adding.map((d) => (
                  <li key={d.index}>
                    <button
                      type="button"
                      className="cl-mics__pick"
                      onClick={() => void add(d)}
                    >
                      {isPhone(d.name) ? (
                        <Smartphone size={16} strokeWidth={1.75} aria-hidden />
                      ) : (
                        <Mic size={16} strokeWidth={1.75} aria-hidden />
                      )}
                      <span className="cl-mics__name">{d.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {problem && <p className="cl-mics__problem">{problem}</p>}
              {adding.length > 0 && (
                <p className="cl-mics__foot">
                  Il enregistre à partir de maintenant.
                </p>
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
                  >
                    {m.lost && !m.muted ? (
                      <TriangleAlert
                        className="cl-mics__lost"
                        size={16}
                        strokeWidth={1.75}
                        aria-label="Plus rien n'arrive"
                      />
                    ) : isPhone(m.device) ? (
                      <Smartphone size={16} strokeWidth={1.75} aria-hidden />
                    ) : (
                      <Mic size={16} strokeWidth={1.75} aria-hidden />
                    )}
                    <span className="cl-mics__name" title={m.device}>
                      {m.device}
                      {m.muted && " · coupé"}
                    </span>
                    <span className="cl-mics__meter">
                      <LevelMeter
                        level={m.muted ? 0 : meterValue(m.rms_db)}
                        peak={m.muted ? 0 : meterValue(m.peak_db)}
                        clipping={!m.muted && m.clipping}
                      />
                    </span>
                    <button
                      type="button"
                      className="cl-mics__icon"
                      aria-pressed={m.muted}
                      title={
                        m.muted ? `Rétablir ${m.device}` : `Couper ${m.device}`
                      }
                      aria-label={
                        m.muted ? `Rétablir ${m.device}` : `Couper ${m.device}`
                      }
                      onClick={() =>
                        void act(() => api.muteTrack(m.sourceId, !m.muted))
                      }
                    >
                      <MicOff size={15} strokeWidth={1.75} aria-hidden />
                    </button>
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
                onClick={() =>
                  void act(() => api.muteMicrophones(!summary.allCut))
                }
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
          )
        }
      >
        <button
          type="button"
          className="cl-mics__more"
          data-open={isOpen || undefined}
          aria-label={`${summary.count === 1 ? "1 micro" : `${summary.count} micros`}${
            summary.cut && !summary.allCut
              ? `, dont ${summary.cut} coupé${summary.cut > 1 ? "s" : ""}`
              : ""
          }${summary.lost ? ", l'un ne répond plus" : ""}. ${isOpen ? "Masquer" : "Voir"} les micros`}
        >
          {summary.allCut ? (
            "Micros coupés"
          ) : (
            <>
              {summary.count > 1 && (
                <span className="cl-mics__count">{summary.count}</span>
              )}
              {summary.cut > 0 && (
                <span>
                  · {summary.cut === 1 ? "1 coupé" : `${summary.cut} coupés`}
                </span>
              )}
            </>
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
              level={meterValue(level.rms_db)}
              peak={meterValue(level.peak_db)}
              clipping={mics.some((m) => !m.muted && m.clipping)}
            />
          </span>
          {isOpen ? (
            <ChevronUp size={12} strokeWidth={1.75} aria-hidden />
          ) : (
            <ChevronDown size={12} strokeWidth={1.75} aria-hidden />
          )}
        </button>
      </Popover>
    </span>
  );
}
