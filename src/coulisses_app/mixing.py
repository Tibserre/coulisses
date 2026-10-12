"""The track the engine hears when a session also has the computer's sound (ADR 0032).

The engine processes one track. For a meeting online or hybrid, it is the microphone and
the computer's sound added together: both were recorded on the microphone's clock, frame
for frame, so the sum stays in the reference's time (every measured time holds). The whole
sum is turned down just enough never to saturate, never compressed. What it was made of
(the sources' fingerprints recorded when each closed, the gain, its own fingerprint) is
written beside it (`mix.json`) and copied into the job that processed it, which outlives
the purge (P7). The raw tracks stay as they are: the mix is made again from them whenever
their recorded fingerprints differ (P5).
"""

from __future__ import annotations

import hashlib
import logging
import os
import struct
import threading
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ValidationError

from coulisses_app import listening, sessions, wav
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import now_iso

log = logging.getLogger(__name__)

MIX_FILE = "mix.wav"
LISTENING_FILE = "listening.wav"
"""What the session's page plays: the microphone turned down while nobody speaks into it
(ADR 0037). The engine never hears it."""
MIX_FACTS = "mix.json"
CEILING = 0.98
"""The loudest sample of the mix, at most (just under full scale)."""
SILENT_PEAK = 1e-6
"""Below this (about -120 dBFS) all along, the computer's sound held nothing: macOS gives
silence, not an error, when its permission is missing."""
CHUNK_FRAMES = 48_000 * 10
RULE = "ref mono + system, times gain (one gain for the whole track)"

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


class MixError(RuntimeError):
    """The mix cannot be made; the message is shown to the user."""


class ListeningMixFacts(BaseModel):
    """What the listening mix was made of (ADR 0037)."""

    file: str
    sha256: str
    gain: float
    rule: str
    parameters: dict[str, float]


class MixFacts(BaseModel):
    """What a mix was made of, and what it holds."""

    made_from: dict[str, str]
    """Source id → its fingerprint, as recorded when it closed."""
    gain: float
    rule: str
    sha256: str
    """The mix's own fingerprint: what the engine received."""
    system_silent: bool
    """The computer's sound held nothing at all: the mix is the microphone alone."""
    made_at: str
    listening_mix: ListeningMixFacts | None = None
    """The mix heard on the session's page; None for a mix made before it existed."""


def _lock(session_id: str) -> threading.Lock:
    with _locks_lock:
        return _locks.setdefault(session_id, threading.Lock())


def busy(session_id: str) -> bool:
    """The mix of this session is being made: its files must not go meanwhile."""
    lock = _locks.get(session_id)
    return lock is not None and lock.locked()


def _layout(path: Path) -> tuple[int, int, int]:
    """(rate, channels, frames) of a WAV written by Coulisses (`wav.py`)."""
    with path.open("rb") as f:
        head = f.read(wav.HEADER_BYTES)
    if len(head) < wav.HEADER_BYTES or head[:4] != b"RIFF" or head[36:40] != b"data":
        log.error("%s is not a WAV written by Coulisses", path)
        raise MixError(
            "Une piste de la séance n'est pas un enregistrement lisible : le micro et le son "
            "de l'ordinateur n'ont pas pu être réunis."
        )
    channels, rate = struct.unpack("<HI", head[22:28])
    (data_bytes,) = struct.unpack("<I", head[40:44])
    return rate, channels, data_bytes // (channels * wav.SAMPLE_BYTES)


def _read(path: Path, channels: int, start: int, count: int) -> NDArray[np.float32]:
    """`count` frames from `start`, as floats, mixed down to one channel."""
    block = channels * wav.SAMPLE_BYTES
    with path.open("rb") as f:
        f.seek(wav.HEADER_BYTES + start * block)
        raw = f.read(count * block)
    usable = len(raw) // block * block
    as_bytes = np.frombuffer(raw[:usable], dtype=np.uint8).reshape(-1, 3)
    as_int = (
        as_bytes[:, 0].astype(np.int32)
        | (as_bytes[:, 1].astype(np.int32) << 8)
        | (as_bytes[:, 2].astype(np.int32) << 16)
    )
    as_int = np.where(as_int >= 1 << 23, as_int - (1 << 24), as_int)
    frames = (as_int.astype(np.float32) / (1 << 23)).reshape(-1, channels)
    return frames.mean(axis=1, dtype=np.float32)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _system_track(data: DataDir, session_id: str) -> sessions.AudioSource | None:
    """The computer's sound, when it holds something to mix."""
    found = next(
        (
            s
            for s in sessions.other_sources(data, session_id)
            if s.source_id == sessions.SYSTEM_SOURCE_ID
        ),
        None,
    )
    if found is None or found.capture_state == "recording":
        return None
    if not found.duration_s:  # nothing recorded, or unreadable: said on the session's page
        return None
    if not found.file_present:
        raise MixError(
            "La piste du son de l'ordinateur est introuvable dans le dossier de la séance. "
            "A-t-elle été déplacée ou supprimée dans le Finder ? Sans elle, les personnes à "
            "distance ne seraient pas entendues."
        )
    return found


def read_facts(data: DataDir, session_id: str) -> MixFacts | None:
    """The mix's facts, once made (None before, or if they cannot be read: then it is made
    again before being used)."""
    facts = data.sources_dir(session_id) / MIX_FACTS
    try:
        return MixFacts.model_validate_json(facts.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValidationError):
        log.warning("unreadable %s: the mix will be made again", facts)
        return None


_asked: set[str] = set()
_asked_lock = threading.Lock()


def listening_path(data: DataDir, session_id: str) -> Path | None:
    """What to play back: the listening mix once made, else the plain mix, else the
    reference. A mix made before the listening one existed gets it, in the background."""
    folder = data.sources_dir(session_id)
    facts = read_facts(data, session_id)
    if facts is not None and facts.listening_mix is not None:
        heard = folder / facts.listening_mix.file
        if heard.is_file():
            return heard
    mix = folder / MIX_FILE
    if facts is not None and mix.is_file():
        with _asked_lock:  # once per service: the player asks for the file many times
            first = session_id not in _asked
            _asked.add(session_id)
        if first:
            prepare_in_background(data, session_id)
        return mix
    return sessions.reference_audio_path(data, session_id)


def processing_input(data: DataDir, session_id: str) -> tuple[Path | None, MixFacts | None]:
    """The track the engine hears, and what it was made of when it is a mix: the mix (made
    now if needed) when the session has the computer's sound, else the reference. Raises
    `MixError`."""
    reference = sessions.reference_source(data, session_id)
    if reference is None:
        return None, None
    ref_path = data.sources_dir(session_id) / reference.file_name
    system = _system_track(data, session_id)
    if system is None or not ref_path.is_file():
        return ref_path, None
    return ensure_mix(data, session_id, reference, system)


def processing_path(data: DataDir, session_id: str) -> Path | None:
    return processing_input(data, session_id)[0]


def ensure_mix(
    data: DataDir,
    session_id: str,
    reference: sessions.AudioSource,
    system: sessions.AudioSource,
) -> tuple[Path, MixFacts]:
    folder = data.sources_dir(session_id)
    ref_path, system_path = folder / reference.file_name, folder / system.file_name
    mix = folder / MIX_FILE
    with _lock(session_id):
        # The fingerprints taken when each recording closed (`finish_capture`).
        made_from = {reference.source_id: reference.sha256, system.source_id: system.sha256}
        known = read_facts(data, session_id)
        heard = folder / LISTENING_FILE
        if (
            known is not None
            and known.made_from == made_from
            and mix.is_file()
            and known.listening_mix is not None
            and heard.is_file()
        ):
            return mix, known
        # Never after the audio was removed (a purge, a deletion): nothing is written back.
        session = sessions.get_session(data, session_id)
        if session is None or session.audio.state == "removed":
            raise MixError("L'audio de cette séance a été supprimé.")
        # A mix made before ADR 0037, from the same sources: only its listening mix is
        # made; the engine's input stays as it was, byte for byte.
        keep_plain = known is not None and known.made_from == made_from and mix.is_file()
        if known is not None:
            log.info(
                "mix of %s: %s",
                session_id,
                "listening mix added" if keep_plain else "made again, its sources changed",
            )
        try:
            gain, system_peak, heard_gain = _mix(
                ref_path, system_path, None if keep_plain else mix, heard
            )
            listening_mix = ListeningMixFacts(
                file=LISTENING_FILE,
                sha256=_sha256(heard),
                gain=heard_gain,
                rule=listening.RULE,
                parameters=listening.PARAMETERS,
            )
            if keep_plain:
                assert known is not None
                facts = known.model_copy(update={"listening_mix": listening_mix})
            else:
                facts = MixFacts(
                    made_from=made_from,
                    gain=gain,
                    rule=RULE,
                    sha256=_sha256(mix),
                    system_silent=system_peak < SILENT_PEAK,
                    made_at=now_iso(),
                    listening_mix=listening_mix,
                )
            partial = folder / f"{MIX_FACTS}.partiel"
            partial.write_text(facts.model_dump_json(indent=2), encoding="utf-8")
            os.replace(partial, folder / MIX_FACTS)
        except MixError:
            raise
        except (OSError, ValueError) as exc:
            log.exception("mixing %s", session_id)
            raise MixError(
                "Le micro et le son de l'ordinateur n'ont pas pu être réunis (le détail est "
                "dans le journal du service). Le disque est-il plein ?"
            ) from exc
        if facts.system_silent:
            log.warning("the computer's sound of %s held nothing at all", session_id)
        return mix, facts


def _mix(
    ref_path: Path, system_path: Path, target: Path | None, heard_target: Path
) -> tuple[float, float, float]:
    """Writes the mix the engine hears (unless `target` is None: it is kept as it is) and
    the one heard on the session's page; returns their gains and the loudest sample of the
    computer's sound."""
    rate, ref_channels, ref_frames = _layout(ref_path)
    system_rate, system_channels, system_frames = _layout(system_path)
    if system_rate != rate:
        raise MixError("Le micro et le son de l'ordinateur n'ont pas la même fréquence.")
    total = max(ref_frames, system_frames)
    frame = max(1, round(rate * listening.FRAME_S))
    step = max(frame, CHUNK_FRAMES - CHUNK_FRAMES % frame)  # whole frames per chunk

    def tracks(start: int) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """(the microphone in mono, the computer's sound) from `start`, as long as each
        other: a shorter track is padded with silence."""
        count = min(step, total - start)
        mic = np.zeros(count, dtype=np.float32)
        computer = np.zeros(count, dtype=np.float32)
        a = _read(ref_path, ref_channels, start, min(count, max(0, ref_frames - start)))
        b = _read(system_path, system_channels, start, min(count, max(0, system_frames - start)))
        mic[: len(a)] = a
        computer[: len(b)] = b
        return mic, computer

    # First: the peaks, and the level of each track every 10 ms.
    peak = system_peak = 0.0
    mic_levels: list[NDArray[np.float64]] = []
    computer_levels: list[NDArray[np.float64]] = []
    for start in range(0, total, step):
        mic, computer = tracks(start)
        peak = max(peak, float(np.max(np.abs(mic + computer), initial=0.0)))
        system_peak = max(system_peak, float(np.max(np.abs(computer), initial=0.0)))
        mic_levels.append(listening.frame_db(mic, frame))
        computer_levels.append(listening.frame_db(computer, frame))
    gains = listening.microphone_gains(
        np.concatenate(mic_levels) if mic_levels else np.zeros(0),
        np.concatenate(computer_levels) if computer_levels else np.zeros(0),
    )

    def heard(
        start: int, mic: NDArray[np.float32], computer: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        mixed = computer + mic * listening.per_sample(gains, frame, start, len(mic))
        return mixed.astype(np.float32, copy=False)

    heard_peak = 0.0
    for start in range(0, total, step):
        mic, computer = tracks(start)
        heard_peak = max(
            heard_peak, float(np.max(np.abs(heard(start, mic, computer)), initial=0.0))
        )
    gain = min(1.0, CEILING / peak) if peak > 0 else 1.0
    heard_gain = min(1.0, CEILING / heard_peak) if heard_peak > 0 else 1.0

    targets = [path for path in (target, heard_target) if path is not None]
    partials = [path.with_name(path.name + ".partiel") for path in targets]
    for partial in partials:
        partial.unlink(missing_ok=True)
    writers = [wav.WavWriter(partial, rate, 1, sync_s=60.0) for partial in partials]
    try:
        for start in range(0, total, step):
            mic, computer = tracks(start)
            if target is not None:
                writers[0].write(((mic + computer) * gain).reshape(-1, 1))
            writers[-1].write((heard(start, mic, computer) * heard_gain).reshape(-1, 1))
    finally:
        for writer in writers:
            writer.close()
    for partial, final in zip(partials, targets, strict=True):
        os.replace(partial, final)
    return gain, system_peak, heard_gain


def prepare_in_background(data: DataDir, session_id: str) -> None:
    """After a recording with the computer's sound: the mix is made at once, to be heard
    on the session's page before the processing gets to it. A failure is logged and asked
    again at the next listening; the processing tries again and says why."""

    def run() -> None:
        try:
            processing_input(data, session_id)
        except Exception:
            log.exception("preparing the mix of %s", session_id)
            with _asked_lock:
                _asked.discard(session_id)

    threading.Thread(target=run, name=f"mix-{session_id}", daemon=True).start()
