/** The place of `enregistrement.riv` (art direction): until the file is drawn, a stand-in
 *  made in code, with the same inputs. `niveau` 0 to 100, `pause`. Rings widen with the
 *  level; paused, they rest. Ink and brick only, a 1.75 stroke, no background. */
export function RecordingVisual({
  niveau,
  pause,
}: {
  niveau: number;
  pause: boolean;
}) {
  const level = pause ? 0 : Math.max(0, Math.min(100, niveau)) / 100;
  const rings = [0, 1, 2];
  return (
    <svg
      className="cl-recvisual"
      viewBox="0 0 200 200"
      role="img"
      aria-hidden
      data-paused={pause || undefined}
    >
      {rings.map((k) => (
        <circle
          key={k}
          cx="100"
          cy="100"
          r={34 + k * 18 + level * (14 + k * 10)}
          className="cl-recvisual__ring"
          style={{ opacity: pause ? 0.18 : 0.55 - k * 0.15 }}
        />
      ))}
      <circle
        cx="100"
        cy="100"
        r={pause ? 24 : 26 + level * 6}
        className="cl-recvisual__core"
      />
    </svg>
  );
}
