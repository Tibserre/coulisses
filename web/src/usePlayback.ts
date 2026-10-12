import { useCallback, useEffect, useRef, useState } from "react";

export interface Playback {
  audioRef: React.RefObject<HTMLAudioElement | null>;
  playing: boolean;
  time: number;
  duration: number | null;
  rate: number;
  error: string | null;
  /** Counts explicit moves (click on a time, previous/next): the transcript follows the
   *  sound only while playing or after such a move, never on first display. */
  moves: number;
  toggle: () => void;
  seek: (t: number, play?: boolean) => void;
  setRate: (rate: number) => void;
  /** Hears a few seconds from `start` (at most up to `end`), then stops and goes back
   *  where one was: enough to recognise a voice. Asked again while heard, it stops. */
  listen: (start: number, end: number) => void;
  /** The start of the excerpt being heard, if one is. */
  excerpt: number | null;
}

/** How long an excerpt is heard at most. */
const EXCERPT_S = 8;

/** Drives the page's <audio> element; the current time is read every frame while playing
 *  so the current word follows the sound smoothly. */
export function usePlayback(): Playback {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState<number | null>(null);
  const [rate, setRateState] = useState(1);
  const [moves, setMoves] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [excerpt, setExcerpt] = useState<number | null>(null);
  const stopAt = useRef<number | null>(null);
  /** Where one was before an excerpt: back there once it is heard. */
  const before = useRef<number | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => {
      setPlaying(false);
      stopAt.current = null;
      setExcerpt(null);
    };
    const onMeta = () =>
      setDuration(Number.isFinite(audio.duration) ? audio.duration : null);
    const onSeeked = () => setTime(audio.currentTime);
    const onError = () =>
      setError(
        "L'audio ne peut pas être lu : fichier introuvable ou format non pris en charge.",
      );
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onPause);
    audio.addEventListener("loadedmetadata", onMeta);
    audio.addEventListener("seeked", onSeeked);
    audio.addEventListener("error", onError);
    return () => {
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onPause);
      audio.removeEventListener("loadedmetadata", onMeta);
      audio.removeEventListener("seeked", onSeeked);
      audio.removeEventListener("error", onError);
    };
  }, []);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const audio = audioRef.current;
      if (audio) {
        setTime(audio.currentTime);
        if (stopAt.current != null && audio.currentTime >= stopAt.current) {
          const back = before.current;
          before.current = null;
          audio.pause();
          if (back != null) {
            audio.currentTime = back;
            setTime(back);
          }
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    stopAt.current = null;
    before.current = null;
    setExcerpt(null);
    if (audio.paused)
      void audio
        .play()
        .catch(() => setError("La lecture n'a pas pu démarrer."));
    else audio.pause();
  }, []);

  const seek = useCallback((t: number, play = true) => {
    const audio = audioRef.current;
    if (!audio) return;
    stopAt.current = null;
    before.current = null;
    setExcerpt(null);
    audio.currentTime = Math.max(0, t);
    setTime(audio.currentTime);
    setMoves((m) => m + 1);
    if (play && audio.paused)
      void audio
        .play()
        .catch(() => setError("La lecture n'a pas pu démarrer."));
  }, []);

  const listen = useCallback(
    (start: number, end: number) => {
      const audio = audioRef.current;
      if (!audio) return;
      if (excerpt === start && !audio.paused) {
        stopAt.current = audio.currentTime; // stops at the next frame, and goes back
        return;
      }
      const from = excerpt === null ? audio.currentTime : before.current;
      seek(start, true);
      before.current = from;
      stopAt.current = Math.min(end, start + EXCERPT_S);
      setExcerpt(start);
    },
    [excerpt, seek],
  );

  const setRate = useCallback((r: number) => {
    if (audioRef.current) audioRef.current.playbackRate = r;
    setRateState(r);
  }, []);

  return {
    audioRef,
    playing,
    time,
    duration,
    rate,
    error,
    moves,
    toggle,
    seek,
    setRate,
    listen,
    excerpt,
  };
}
