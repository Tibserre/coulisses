"""The mix heard on the session's page (ADR 0037): the microphone turned down while nobody
speaks into it (the keyboard, the room), and while only the computer speaks.

The engine does not hear it: it keeps the plain sum (`mixing.py`, ADR 0032). Speech is told
from a keystroke by how long it lasts: a click is gone in a few hundredths of a second, a
syllable lasts. The whole recording is known when this runs, so the microphone comes back
up a little before speech starts: no word loses its beginning. Nothing moves in time: only
the level changes, softly.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FRAME_S = 0.01
"""The level is measured every 10 ms."""
SILENT_DB = -120.0
FLOOR_PERCENTILE = 10
"""The track's background noise: its quietest tenth."""
ACTIVE_ABOVE_DB = 10.0
"""Speech stands this far above the background noise."""
MIN_SPEECH_S = 0.12
"""Shorter than this, it is a click (a key, a knock), not speech."""
BRIDGE_S = 0.25
"""The gaps between syllables and words, bridged."""
LEAD_S = 0.15
"""The microphone comes back up this long before speech starts."""
HOLD_S = 0.4
"""And stays up this long after it ends."""
QUIET_DB = -12.0
"""The microphone while nobody speaks: turned down, never muted."""
DUCK_DB = -15.0
"""The microphone while only the computer speaks (someone online)."""
SMOOTH_S = 0.06
"""The level changes over this long: no click, no pumping."""

PARAMETERS = {
    "frame_s": FRAME_S,
    "active_above_db": ACTIVE_ABOVE_DB,
    "min_speech_s": MIN_SPEECH_S,
    "bridge_s": BRIDGE_S,
    "lead_s": LEAD_S,
    "hold_s": HOLD_S,
    "quiet_db": QUIET_DB,
    "duck_db": DUCK_DB,
    "smooth_s": SMOOTH_S,
}
RULE = (
    "system + ref mono * g(t), then one gain for the whole track; g(t) = 1 while someone "
    f"speaks into the microphone, {DUCK_DB:g} dB while only the computer speaks, "
    f"{QUIET_DB:g} dB otherwise"
)


def frame_db(samples: NDArray[np.float32], frame: int) -> NDArray[np.float64]:
    """The level (RMS, dBFS) of each frame of `frame` samples (a last partial one too)."""
    if not len(samples):
        return np.zeros(0)
    count = -(-len(samples) // frame)
    padded = np.zeros(count * frame, dtype=np.float64)
    padded[: len(samples)] = samples
    rms = np.sqrt(np.mean(padded.reshape(count, frame) ** 2, axis=1))
    with np.errstate(divide="ignore"):
        return np.maximum(20 * np.log10(rms), SILENT_DB)


def _runs(mask: NDArray[np.bool_]) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
    """(starts, ends) of each run of True, ends exclusive."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)


def speaking(level_db: NDArray[np.float64], frame_s: float = FRAME_S) -> NDArray[np.bool_]:
    """For each frame: someone speaks on this track (a click does not count)."""
    if not len(level_db):
        return np.zeros(0, dtype=bool)
    floor = max(float(np.percentile(level_db, FLOOR_PERCENTILE)), SILENT_DB)
    active = level_db > floor + ACTIVE_ABOVE_DB
    # Clicks out first, then the gaps between syllables bridged.
    starts, ends = _runs(active)
    shortest = round(MIN_SPEECH_S / frame_s)
    kept = np.zeros_like(active)
    for start, end in zip(starts, ends, strict=True):
        if end - start >= shortest:
            kept[start:end] = True
    starts, ends = _runs(~kept)
    bridge = round(BRIDGE_S / frame_s)
    for start, end in zip(starts, ends, strict=True):
        if start > 0 and end < len(kept) and end - start <= bridge:
            kept[start:end] = True
    # Up a little before, down a while after.
    starts, ends = _runs(kept)
    widened = np.zeros_like(kept)
    lead, hold = round(LEAD_S / frame_s), round(HOLD_S / frame_s)
    for start, end in zip(starts, ends, strict=True):
        widened[max(0, start - lead) : min(len(kept), end + hold)] = True
    return widened


def microphone_gains(
    microphone_db: NDArray[np.float64],
    system_db: NDArray[np.float64],
    frame_s: float = FRAME_S,
) -> NDArray[np.float64]:
    """The microphone's gain (linear) for each frame, smoothed."""
    count = max(len(microphone_db), len(system_db))
    mic = np.zeros(count, dtype=bool)
    computer = np.zeros(count, dtype=bool)
    mic[: len(microphone_db)] = speaking(microphone_db, frame_s)
    computer[: len(system_db)] = speaking(system_db, frame_s)
    db = np.where(mic, 0.0, np.where(computer, DUCK_DB, QUIET_DB))
    gains = 10 ** (db / 20)
    width = max(1, round(SMOOTH_S / frame_s))
    if width > 1 and count:
        padded = np.pad(gains, (width // 2, width - 1 - width // 2), mode="edge")
        gains = np.convolve(padded, np.ones(width) / width, mode="valid")
    return gains


def per_sample(
    gains: NDArray[np.float64], frame: int, start: int, count: int
) -> NDArray[np.float32]:
    """The frame gains, as one per sample from `start` (linear between frame centres)."""
    if not count:
        return np.zeros(0, dtype=np.float32)
    centres = np.arange(len(gains)) * frame + frame / 2
    positions = np.arange(start, start + count, dtype=np.float64)
    return np.interp(positions, centres, gains).astype(np.float32)
