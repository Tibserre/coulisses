"""The measured waveform of the sound a session's page plays (ADR 0092): the peak of each
`STEP_S`, read from the listening file by ffmpeg, never made from the turns' times (P2). Kept
in the session's folder, beside `sources/`: it outlives the purge of the audio (decided by
the user). Measured again in the background when the file played is replaced."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from coulisses_app import disk, lossless, retention, sessions
from coulisses_app.paths import DataDir

log = logging.getLogger(__name__)

STEP_S = 0.05
RATE = 48_000
FLOOR_DB = -120.0
"""Silence: a peak under a millionth of full scale."""
FILE = "onde.json"


class Waveform(BaseModel):
    """L'onde de la séance (glossary): measured on the sound the page plays."""

    heard_version: str
    """The file measured (`heard_version`)."""
    duration_s: float
    levels_db: list[float]
    """The peak of each slice of the sound, in dBFS (`FLOOR_DB` at least)."""


class NotReady(Exception):
    """Being measured, or nothing to measure yet (a recording under way)."""


class NoWaveform(Exception):
    """Nothing to measure, or the measure failed: said, in French."""


def heard_version(data: DataDir, session_id: str) -> str | None:
    """Changes when the file the page plays is replaced (a listening mix made, a track put in
    an MP4). None without a sound to play, or while it records (the file grows)."""
    reference = sessions.reference_source(data, session_id)
    if reference is not None and reference.capture_state == "recording":
        return None
    if retention.audio_status(data, session_id).state == "removed":
        return None
    path = lossless.heard_path(data, session_id)
    if path is None:
        return None
    try:
        facts = path.stat()
    except FileNotFoundError:  # moved in the Finder: the player says it
        return None
    return f"{path.name}-{facts.st_mtime_ns}-{facts.st_size}"


def levels(data: DataDir, session_id: str, bars: int) -> Waveform:
    """`bars` levels, each the loudest of its slices. Raises `NotReady` while it is measured
    (started here if needed) or while it records, `NoWaveform` when there is none to give."""
    reference = sessions.reference_source(data, session_id)
    if reference is not None and reference.capture_state == "recording":
        raise NotReady
    kept = _read(data, session_id)
    if retention.audio_status(data, session_id).state == "removed":
        if kept is None:
            raise NoWaveform(
                "L'audio de cette séance a été supprimé avant que son onde soit mesurée."
            )
        return _bars(kept, bars)  # kept after the purge (decided by the user)
    version = heard_version(data, session_id)
    if version is None:
        raise NoWaveform("Le son de cette séance est introuvable : il n'y a rien à mesurer.")
    if kept is not None and kept.heard_version == version:
        return _bars(kept, bars)
    with _measuring_lock:
        failed = _failed.get(session_id) == version
    if failed:
        raise NoWaveform(
            "L'onde du son n'a pas pu être mesurée (le détail est dans le journal du service)."
        )
    _measure_in_background(data, session_id)
    raise NotReady


def keep(data: DataDir, session_id: str) -> str | None:
    """Before the audio goes: its waveform measured if it is not yet (it outlives the purge).
    A failure never holds the purge back: returned, said with it."""
    with _measuring_lock:
        if session_id in _measuring:
            return None  # the purge is refused meanwhile (`busy`), and tried again
        _measuring.add(session_id)
    try:
        version = heard_version(data, session_id)
        kept = _read(data, session_id)
        if version is not None and (kept is None or kept.heard_version != version):
            _measure(data, session_id, version)
        return None
    except retention.NotFoundError:
        return None  # no such session: the removal says it
    except Exception as exc:
        log.exception("measuring the waveform of %s before its audio goes", session_id)
        return f"l'onde du son n'a pas pu être mesurée avant la suppression ({exc})"
    finally:
        with _measuring_lock:
            _measuring.discard(session_id)


def busy(session_id: str) -> bool:
    """Its waveform being written in the session's folder: not deleted meanwhile."""
    with _measuring_lock:
        return session_id in _measuring


def _bars(kept: Waveform, bars: int) -> Waveform:
    levels = kept.levels_db
    if not levels:
        return kept
    count = min(bars, len(levels))
    grouped = [
        max(levels[i * len(levels) // count : (i + 1) * len(levels) // count]) for i in range(count)
    ]
    return kept.model_copy(update={"levels_db": grouped})


def _read(data: DataDir, session_id: str) -> Waveform | None:
    path = data.session_dir(session_id) / FILE
    if not path.is_file():
        return None
    return Waveform.model_validate_json(path.read_text(encoding="utf-8"))


def measure(path: Path) -> tuple[float, list[float]]:
    """(duration, the peak of each `STEP_S` in dBFS) of the sound in `path`, mixed to mono."""
    command = [
        *("ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0"),
        *("-ac", "1", "-ar", str(RATE), "-f", "f32le", "pipe:1"),
    ]
    step = int(RATE * STEP_S)
    peaks: list[float] = []
    samples = 0
    rest = np.zeros(0, dtype=np.float32)
    # Its errors to a file, never a pipe (`lossless.decoded_pcm_sha256`).
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
            assert process.stdout is not None
            while chunk := process.stdout.read(step * 4 * 1000):
                block = np.concatenate([rest, np.frombuffer(chunk, dtype="<f4")])
                whole = len(block) // step * step
                peaks.extend(np.abs(block[:whole]).reshape(-1, step).max(axis=1).tolist())
                samples += whole
                rest = block[whole:]
        if process.returncode != 0:
            errors.seek(0)
            said = errors.read().decode(errors="replace").strip()
            raise lossless.ConversionError(f"ffmpeg n'a pas pu relire {path.name} : {said}")
    if len(rest):
        peaks.append(float(np.abs(rest).max()))
        samples += len(rest)
    floor = 10 ** (FLOOR_DB / 20)
    return samples / RATE, [round(20 * float(np.log10(max(p, floor))), 1) for p in peaks]


_measuring: set[str] = set()
_failed: dict[str, str] = {}
"""The version whose measure failed, by session: not tried again until the sound changes."""
_measuring_lock = threading.Lock()


def _measure(data: DataDir, session_id: str, version: str) -> None:
    path = lossless.heard_path(data, session_id)
    if path is None:
        return
    duration, peaks = measure(path)
    # Replaced while it was measured: measured again at the next look.
    if heard_version(data, session_id) == version:
        _write(
            data, session_id, Waveform(heard_version=version, duration_s=duration, levels_db=peaks)
        )


def _measure_in_background(data: DataDir, session_id: str) -> None:
    with _measuring_lock:
        if session_id in _measuring:
            return
        _measuring.add(session_id)

    def run() -> None:
        version: str | None = None
        try:
            version = heard_version(data, session_id)
            if version is not None:
                _measure(data, session_id, version)
        except Exception:
            log.exception("measuring the waveform of %s", session_id)
            if version is not None:
                with _measuring_lock:
                    _failed[session_id] = version
        finally:
            with _measuring_lock:
                _measuring.discard(session_id)

    threading.Thread(target=run, name=f"onde-{session_id}", daemon=True).start()


def _write(data: DataDir, session_id: str, made: Waveform) -> None:
    """Replaced whole, never half written."""
    folder = data.session_dir(session_id)
    partial = folder / f"{FILE}.partiel"
    partial.write_text(made.model_dump_json(), encoding="utf-8")
    disk.sync_file(partial)
    os.replace(partial, folder / FILE)
    disk.sync_folder(folder)
