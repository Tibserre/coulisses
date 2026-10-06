"""Recording a session from the Mac's microphone, by the service (ADR 0005, 0027).

The microphone is read as it is (no noise reduction, no echo cancelling, no automatic
gain) at 48 kHz and written as it comes, to a WAV file kept true on disk (`wav.py`).
Closing the interface does not stop it. While it records, the Mac does not go to sleep.
One recording at a time. Whatever goes wrong, the session ends up closed and said so:
never left « recording » while the service runs (P8).
"""

from __future__ import annotations

import logging
import math
import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

from coulisses_app import marks, sessions, wav
from coulisses_app.paths import DataDir
from coulisses_app.spaces import SpaceError
from coulisses_app.storage.db import connect

log = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
MAX_CHANNELS = 2
LOW_DB = -50.0
"""Below this level (RMS, dBFS) for `LOW_AFTER_S`, the input is said to be too quiet."""
LOW_AFTER_S = 10.0
CLIP_DB = -0.1
"""A peak at or above this is a saturation, shown for `CLIP_SHOWN_S`."""
CLIP_SHOWN_S = 2.0
SILENT_DB = -120.0
SILENT_STREAM_S = 3.0
"""No block at all from the microphone for this long: it stopped delivering."""


class RecordingError(SpaceError):
    """A recording that cannot start, go on or stop; the message is shown to the user."""


class InputDevice(BaseModel):
    index: int
    name: str
    channels: int
    default: bool


class Levels(BaseModel):
    peak_db: float
    rms_db: float


class RecordingState(BaseModel):
    session_id: str
    state: Literal["recording", "paused"]
    elapsed_s: float
    """Recorded so far (pauses left out): the time markers and notes are set at."""
    device: str
    channels: int
    levels: Levels
    too_quiet: bool
    """The input has been very low for a while: wrong microphone, too far, or no access."""
    clipping: bool
    """The input saturated a moment ago."""
    dropouts: int = 0
    """Times the Mac could not keep up and lost some sound (input overflow)."""
    error: str | None = None
    """Writing stopped, or the microphone stopped delivering: what was recorded is kept."""
    markers: list[marks.Marker] = []
    """Set so far: play and discussion switches, key moments."""
    notes: list[marks.TimedNote] = []


class InputStream(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


OnBlock = Callable[[NDArray[np.float32], bool], None]
"""Called with each block from the microphone, and whether sound was lost before it."""

StreamFactory = Callable[[int, int, OnBlock], InputStream]
"""(device index, channels, on_block) → a stream, not started."""


def input_devices() -> list[InputDevice]:
    import sounddevice as sd  # pyright: ignore[reportMissingTypeStubs]  # PortAudio, untyped

    default_in = sd.default.device[0]
    listed: list[dict[str, Any]] = list(sd.query_devices())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    found: list[InputDevice] = []
    for index, info in enumerate(listed):
        channels = int(info["max_input_channels"])
        if channels > 0:
            found.append(
                InputDevice(
                    index=index,
                    name=str(info["name"]),
                    channels=channels,
                    default=index == default_in,
                )
            )
    return found


def _sounddevice_stream(device: int, channels: int, on_block: OnBlock) -> InputStream:
    import sounddevice as sd  # pyright: ignore[reportMissingTypeStubs]  # PortAudio, untyped

    def callback(indata: NDArray[np.float32], _frames: int, _time: Any, status: Any) -> None:
        # Real time: no logging here; a lost block is counted and shown (P8).
        on_block(indata.copy(), bool(status.input_overflow))

    return sd.InputStream(
        samplerate=SAMPLE_RATE,
        device=device,
        channels=channels,
        dtype="float32",
        callback=callback,
    )


def _db(value: float) -> float:
    return 20 * math.log10(value) if value > 0 else SILENT_DB


def battery_in(pmset_output: str) -> bool:
    """What `pmset -g batt` says: on battery or not."""
    return "'Battery Power'" in pmset_output


def on_battery() -> bool:
    """The Mac runs on its battery (pmset); False if it cannot be told (logged)."""
    if shutil.which("pmset") is None:
        log.warning("pmset not found: the power source cannot be told")
        return False
    try:
        out = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("pmset failed: %s", exc)
        return False
    return battery_in(out)


class KeepAwake:
    """Keeps the Mac from idle sleep while something holds it (recording, processing),
    with macOS's own `caffeinate`, tied to this process: if the service dies, the Mac
    may sleep again. Counted: the last release lets it sleep. Never raises."""

    def __init__(self, command: list[str] | None = None) -> None:
        self._command = (
            command if command is not None else ["caffeinate", "-i", "-w", str(os.getpid())]
        )
        self._holders = 0
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def hold(self) -> None:
        with self._lock:
            self._holders += 1
            if self._process is not None or not self._command:
                return
            if shutil.which(self._command[0]) is None:
                log.warning("%s not found: the Mac may go to sleep", self._command[0])
                return
            try:
                self._process = subprocess.Popen(self._command)
            except OSError as exc:
                log.warning("cannot keep the Mac awake: %s", exc)

    def release(self) -> None:
        with self._lock:
            self._holders = max(0, self._holders - 1)
            if self._holders == 0 and self._process is not None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None


@dataclass
class _Flags:
    paused: bool = False


Block = tuple[NDArray[np.float32], bool, bool]
"""A block from the microphone, whether sound was lost before it, and whether the
recording was paused when it was heard."""


@dataclass
class _Recording:
    session_id: str
    device: str
    channels: int
    writer: wav.WavWriter
    stream: InputStream
    flags: _Flags
    blocks: queue.Queue[Block | None]
    levels: Levels = field(default_factory=lambda: Levels(peak_db=SILENT_DB, rms_db=SILENT_DB))
    quiet_since: float | None = None
    clipped_at: float | None = None
    dropouts: int = 0
    error: str | None = None
    writer_thread: threading.Thread | None = None
    last_block_at: float = 0.0
    markers: list[marks.Marker] = field(default_factory=lambda: list[marks.Marker]())
    notes: list[marks.TimedNote] = field(default_factory=lambda: list[marks.TimedNote]())


class StopResult(BaseModel):
    session_id: str
    duration_s: float
    processing: bool
    """The processing was queued; not on battery (the user decides, spec §7.4)."""
    on_battery: bool


def _close_quietly(stream: InputStream) -> str | None:
    """Stop and close the microphone; what went wrong, if anything (never raised: the file
    must be closed after it, whatever the microphone does)."""
    problems: list[str] = []
    for step in (stream.stop, stream.close):
        try:
            step()
        except Exception as exc:  # PortAudio's errors: logged in full, the file comes first
            log.exception("microphone %s", step.__name__)
            problems.append(str(exc))
    return "; ".join(problems) or None


class Recorder:
    def __init__(
        self,
        data: DataDir,
        *,
        stream_factory: StreamFactory = _sounddevice_stream,
        devices: Callable[[], list[InputDevice]] = input_devices,
        keep_awake: KeepAwake | None = None,
        battery: Callable[[], bool] = on_battery,
        clock: Callable[[], float] = time.monotonic,
        max_data_bytes: int = wav.MAX_DATA_BYTES,
    ) -> None:
        self.data = data
        self._stream_factory = stream_factory
        self._devices = devices
        self.keep_awake = keep_awake or KeepAwake()
        self._battery = battery
        self._clock = clock
        self._max_data_bytes = max_data_bytes
        self._lock = threading.Lock()
        self._current: _Recording | None = None

    # -- the recording --------------------------------------------------------------------

    def start(
        self,
        *,
        space_id: int | None,
        attendee_ids: list[int],
        unnamed_attendees: int | None,
        device_index: int | None,
    ) -> RecordingState:
        with self._lock:
            if self._current is not None:
                raise RecordingError("Un enregistrement est déjà en cours.")
            devices = self._devices()
            if device_index is None:
                chosen = next((d for d in devices if d.default), devices[0] if devices else None)
            else:
                chosen = next((d for d in devices if d.index == device_index), None)
            if chosen is None:
                raise RecordingError(
                    "Aucun micro trouvé : branchez-en un, ou choisissez-en un autre."
                )
            channels = min(chosen.channels, MAX_CHANNELS)
            blocks: queue.Queue[Block | None] = queue.Queue()
            flags = _Flags()

            def heard(block: NDArray[np.float32], lost: bool) -> None:
                # Paused or not when heard, not when written: a pause cuts exactly there.
                blocks.put((block, lost, flags.paused))

            # The microphone is opened and started before the session is made: one that
            # refuses leaves nothing behind (its first blocks wait in the queue).
            try:
                stream = self._stream_factory(chosen.index, channels, heard)
            except Exception as exc:
                raise RecordingError(
                    f"Le micro « {chosen.name} » n'a pas pu être ouvert : {exc}"
                ) from exc
            try:
                stream.start()
            except Exception as exc:
                _close_quietly(stream)
                raise RecordingError(
                    f"Le micro « {chosen.name} » n'a pas pu démarrer. Sur macOS, l'accès au "
                    "micro se donne dans Réglages Système, Confidentialité et sécurité, Micro, "
                    f"à l'application qui lance Coulisses. ({exc})"
                ) from exc
            try:
                session_id, path = sessions.start_capture(
                    self.data,
                    space_id=space_id,
                    attendee_ids=attendee_ids,
                    unnamed_attendees=unnamed_attendees,
                    device=chosen.name,
                    sample_rate=SAMPLE_RATE,
                    channels=channels,
                )
            except Exception:
                _close_quietly(stream)
                raise
            try:
                writer = wav.WavWriter(
                    path, SAMPLE_RATE, channels, max_data_bytes=self._max_data_bytes
                )
            except Exception as exc:
                _close_quietly(stream)
                sessions.close_empty_capture(self.data, session_id, reason=str(exc))
                raise RecordingError(
                    f"Le fichier de l'enregistrement n'a pas pu être créé : {exc}"
                ) from exc
            recording = _Recording(
                session_id=session_id,
                device=chosen.name,
                channels=channels,
                writer=writer,
                stream=stream,
                flags=flags,
                blocks=blocks,
                last_block_at=self._clock(),
            )
            recording.writer_thread = threading.Thread(
                target=self._write, args=(recording,), name="capture-writer", daemon=True
            )
            recording.writer_thread.start()
            self.keep_awake.hold()
            self._current = recording
            return self._state(recording)

    def _write(self, recording: _Recording) -> None:
        """Drains the blocks from the microphone: levels always, audio unless paused. A
        failure to write stops writing, keeps what is there and says why (P8)."""
        while (item := recording.blocks.get()) is not None:
            block, lost, paused = item
            peak = float(np.max(np.abs(block))) if block.size else 0.0
            rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
            now = self._clock()
            recording.last_block_at = now
            recording.dropouts += int(lost)
            recording.levels = Levels(peak_db=_db(peak), rms_db=_db(rms))
            if recording.levels.peak_db >= CLIP_DB:
                recording.clipped_at = now
            if recording.levels.rms_db < LOW_DB:
                recording.quiet_since = recording.quiet_since or now
            else:
                recording.quiet_since = None
            if paused or recording.error is not None:
                continue
            try:
                recording.writer.write(block)
            except wav.WavFullError as exc:
                recording.error = f"L'enregistrement est arrêté : {exc}."
            except Exception as exc:  # disk full…: written so far is kept
                recording.error = (
                    f"L'écriture sur le disque a échoué : {exc}. Ce qui précède est gardé."
                )
                log.exception("capture of %s", recording.session_id)

    def _state(self, recording: _Recording) -> RecordingState:
        now = self._clock()
        return RecordingState(
            session_id=recording.session_id,
            state="paused" if recording.flags.paused else "recording",
            elapsed_s=recording.writer.frames / SAMPLE_RATE,
            device=recording.device,
            channels=recording.channels,
            levels=recording.levels,
            too_quiet=not recording.flags.paused
            and recording.quiet_since is not None
            and now - recording.quiet_since >= LOW_AFTER_S,
            clipping=recording.clipped_at is not None
            and now - recording.clipped_at <= CLIP_SHOWN_S,
            dropouts=recording.dropouts,
            markers=list(recording.markers),
            notes=list(recording.notes),
            error=recording.error
            or (
                "Le micro ne donne plus de son depuis quelques secondes : est-il débranché ? "
                "Ce qui est enregistré est gardé."
                if now - recording.last_block_at > SILENT_STREAM_S
                else None
            ),
        )

    def state(self) -> RecordingState | None:
        with self._lock:
            return self._state(self._current) if self._current else None

    def pause(self) -> RecordingState:
        return self._set_paused(True)

    def resume(self) -> RecordingState:
        return self._set_paused(False)

    def _set_paused(self, paused: bool) -> RecordingState:
        with self._lock:
            if self._current is None:
                raise RecordingError("Aucun enregistrement en cours.")
            self._current.flags.paused = paused
            return self._state(self._current)

    # -- what is marked while recording (6b) --------------------------------------------

    def mark(self, kind: marks.MarkerKind, at_s: float | None = None) -> RecordingState:
        """A marker now, at the time recorded so far (pauses left out); or at a time given,
        already recorded (a marker taken back by mistake, put back)."""
        with self._lock:
            recording = self._require()
            elapsed = recording.writer.frames / SAMPLE_RATE
            if at_s is None:
                at_s = elapsed
            elif not 0 <= at_s <= elapsed:
                raise RecordingError("Ce marqueur tombe hors de l'enregistrement.")
            conn = connect(self.data)
            try:
                recording.markers.append(marks.add_marker(conn, recording.session_id, kind, at_s))
            finally:
                conn.close()
            return self._state(recording)

    def note(self, text: str, at_s: float) -> RecordingState:
        """A note, at the time its first letter was typed (given by the interface): it
        belongs where it was thought of, not where it was finished."""
        with self._lock:
            recording = self._require()
            elapsed = recording.writer.frames / SAMPLE_RATE
            if not 0 <= at_s <= elapsed + 1:
                raise RecordingError("Cette note tombe hors de l'enregistrement.")
            conn = connect(self.data)
            try:
                recording.notes.append(
                    marks.add_timed_note(conn, recording.session_id, min(at_s, elapsed), text)
                )
            finally:
                conn.close()
            return self._state(recording)

    def take_back(self, what: Literal["marker", "note"], item_id: int) -> RecordingState:
        with self._lock:
            recording = self._require()
            conn = connect(self.data)
            try:
                marks.remove(conn, recording.session_id, what, item_id)
            finally:
                conn.close()
            if what == "marker":
                recording.markers = [m for m in recording.markers if m.id != item_id]
            else:
                recording.notes = [n for n in recording.notes if n.id != item_id]
            return self._state(recording)

    def _require(self) -> _Recording:
        if self._current is None:
            raise RecordingError("Aucun enregistrement en cours.")
        return self._current

    def stop(self, *, profile: str) -> StopResult:
        """Stop, close the file, describe it; queue the processing unless on battery.
        Whatever the microphone does, the session is closed with what is on disk."""
        with self._lock:
            recording = self._current
            if recording is None:
                raise RecordingError("Aucun enregistrement en cours.")
            self._current = None
        microphone = _close_quietly(recording.stream)
        recording.blocks.put(None)
        if recording.writer_thread is not None:
            recording.writer_thread.join()
        try:
            recording.writer.close()
        except OSError as exc:  # its last header write: `repair` below makes it true
            log.warning("closing %s: %s", recording.writer.path, exc)
        finally:
            self.keep_awake.release()
        # From what is on disk, whatever the writer managed: the header is made true.
        try:
            frames = wav.repair(recording.writer.path)
            sessions.finish_capture(self.data, recording.session_id, frames=frames)
        except Exception as exc:
            log.exception("closing the recording of %s", recording.session_id)
            sessions.close_empty_capture(
                self.data, recording.session_id, reason=str(exc), unreadable=True
            )
            raise RecordingError(
                f"L'enregistrement est arrêté, mais son fichier n'a pas pu être relu : {exc}. "
                "Il reste dans le dossier de la séance."
            ) from exc
        battery = self._battery()
        processing = frames > 0 and not battery
        if processing:
            sessions.start_processing(self.data, recording.session_id, profile=profile)
        if microphone:
            log.warning(
                "recording %s stopped, microphone said: %s", recording.session_id, microphone
            )
        return StopResult(
            session_id=recording.session_id,
            duration_s=frames / SAMPLE_RATE,
            processing=processing,
            on_battery=battery,
        )

    def shutdown(self, *, profile: str) -> None:
        """The service stops: a recording in progress is closed properly, not lost."""
        if self.state() is not None:
            self.stop(profile=profile)


def recover_interrupted(data: DataDir) -> list[str]:
    """At start: recordings left unfinished by a crash are repaired and kept, never
    processed without the user. Returns what to tell them. Never stops the service from
    starting: what cannot be repaired is said."""
    told: list[str] = []
    for session_id in sessions.interrupted_captures(data):
        path = data.sources_dir(session_id) / sessions.CAPTURE_FILE
        try:
            frames = wav.repair(path)
            sessions.finish_capture(data, session_id, frames=frames, state="recovered")
        except Exception as exc:
            log.exception("recovering the recording of %s", session_id)
            sessions.close_empty_capture(data, session_id, reason=str(exc), unreadable=True)
            told.append(f"Enregistrement interrompu illisible ({session_id}) : {exc}")
            continue
        minutes = frames / SAMPLE_RATE / 60
        told.append(
            f"Enregistrement interrompu récupéré ({session_id}, {minutes:.0f} min) : "
            "ouvrez la séance pour lancer son traitement."
        )
    return told
