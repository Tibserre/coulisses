"""Recording a session from the Mac's microphone, by the service (ADR 0005, 0027).

The microphone is read as it is (no noise reduction, no echo cancelling, no automatic
gain) at 48 kHz and written as it comes, to a WAV file kept true on disk (`wav.py`).
Closing the interface does not stop it. While it records, the Mac does not go to sleep.
For a meeting online or hybrid, the computer's sound is recorded with it, on its clock, into
a file of its own (`system_audio.py`, ADR 0032). One recording at a time. Whatever goes
wrong, the session ends up closed and said so: never left « recording » while the service
runs (P8).
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

from coulisses_app import marks, mixing, sessions, system_audio, wav
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


SYSTEM_SILENT = (
    "Le son de l'ordinateur est resté muet du début à la fin : macOS ne l'a sans doute pas "
    "donné. Autorisez-le dans Réglages Système, Confidentialité et sécurité, Enregistrement "
    "de l'écran et de l'audio du système. Le micro seul est traité."
)


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
    extra: list[TrackState] = []
    """The microphones added, recording at the same time (ADR 0031, 0033), each with its
    own alerts."""
    system: TrackState | None = None
    """The computer's sound, recorded with the microphone (ADR 0032). Silence is normal
    there: `too_quiet` only says it has been silent for a while."""


class TrackState(BaseModel):
    """A track beside the main one (a microphone added, the computer's sound), as the
    recording screen shows it."""

    device: str
    levels: Levels
    too_quiet: bool
    clipping: bool
    dropouts: int = 0
    error: str | None = None
    """It stopped (unplugged, the iPhone gone away, the disk…): the main recording goes on;
    what it recorded is kept."""


class InputStream(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


OnBlock = Callable[[NDArray[np.float32], bool], None]
"""Called with each block from the microphone, and whether sound was lost before it."""

StreamFactory = Callable[[int, int, OnBlock], InputStream]
"""(device index, channels, on_block) → a stream, not started."""

SystemStreamFactory = Callable[[str, int, OnBlock], InputStream]
"""(microphone's name, its channels, on_block) → the microphone and the computer's sound as
one stream, not started: each block holds the microphone's channels, then the computer's."""


def _system_stream(microphone: str, channels: int, on_block: OnBlock) -> InputStream:
    return system_audio.HelperStream(microphone, channels, on_block)


class _Shared:
    """The stream of a track fed by another track's stream (the computer's sound, by the
    microphone's): stopped and closed with it."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


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


def refresh_devices() -> None:
    """PortAudio reads the list of microphones once, when it starts, and keeps it. A device
    that comes and goes (the iPhone through Continuity, each time it wakes) gets a new
    identity in macOS: opened from the old list, it fails (« Internal »). Read again; only
    with no stream open (ADR 0031)."""
    import sounddevice as sd  # pyright: ignore[reportMissingTypeStubs]  # PortAudio, untyped

    # The documented way to read the devices again.
    sd._terminate()  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
    sd._initialize()  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]


OPEN_TRIES = 3
"""A microphone that is waking up (the iPhone, a second or two) is tried again."""


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
class _Track:
    """One microphone and its file: the reference, or one added (ADR 0031, 0033)."""

    source_id: str
    device: str
    channels: int
    writer: wav.WavWriter
    stream: InputStream
    blocks: queue.Queue[Block | None]
    levels: Levels = field(default_factory=lambda: Levels(peak_db=SILENT_DB, rms_db=SILENT_DB))
    quiet_since: float | None = None
    clipped_at: float | None = None
    dropouts: int = 0
    error: str | None = None
    writer_thread: threading.Thread | None = None
    last_block_at: float = 0.0
    loudest: float = 0.0
    """The loudest sample written: a computer's sound that stayed at 0 held nothing."""


@dataclass
class _Opened:
    """A track whose stream is open, before its file is made."""

    source_id: str
    device: str
    channels: int
    stream: InputStream
    blocks: queue.Queue[Block | None]


def _heard(blocks: queue.Queue[Block | None], flags: _Flags) -> OnBlock:
    def heard(block: NDArray[np.float32], lost: bool) -> None:
        # Paused or not when heard, not when written: a pause cuts exactly there, on
        # every microphone at once.
        blocks.put((block, lost, flags.paused))

    return heard


@dataclass
class _Recording:
    session_id: str
    flags: _Flags
    tracks: list[_Track]
    """The reference first; its time is the recording's (markers, notes)."""
    markers: list[marks.Marker] = field(default_factory=lambda: list[marks.Marker]())
    notes: list[marks.TimedNote] = field(default_factory=lambda: list[marks.TimedNote]())

    @property
    def main(self) -> _Track:
        return self.tracks[0]


class StopResult(BaseModel):
    session_id: str
    duration_s: float
    processing: bool
    """The processing was queued; not on battery (the user decides, spec §7.4)."""
    on_battery: bool
    second_problem: str | None = None
    """What went wrong with the other tracks (a file not read back, the computer's sound
    silent all along): said after stopping."""


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
        refresh: Callable[[], None] | None = None,
        retry_wait_s: float = 1.0,
        system_stream_factory: SystemStreamFactory = _system_stream,
    ) -> None:
        self.data = data
        self._stream_factory = stream_factory
        self._system_stream_factory = system_stream_factory
        self._devices = devices
        self.keep_awake = keep_awake or KeepAwake()
        self._battery = battery
        self._clock = clock
        self._max_data_bytes = max_data_bytes
        # The real list is read again; a list given (tests) needs nothing.
        self._refresh = refresh or (refresh_devices if devices is input_devices else lambda: None)
        self._retry_wait_s = retry_wait_s
        self._lock = threading.Lock()
        self._closing = False
        """A recording being stopped: its streams are still open, the list is not re-read."""
        self._current: _Recording | None = None

    # -- the recording --------------------------------------------------------------------

    def list_devices(self) -> list[InputDevice]:
        """The microphones as macOS sees them now (read again unless a recording runs: the
        list cannot be re-read with a stream open)."""
        with self._lock:
            self._fresh()
            return self._devices()

    def _fresh(self) -> None:
        """Re-read the microphones, never with a stream open (recording, or being stopped):
        PortAudio would cut them. Under the lock."""
        if self._current is not None or self._closing:
            return
        try:
            self._refresh()
        except Exception as exc:
            log.exception("re-reading the microphones")
            raise RecordingError(
                "La liste des micros n'a pas pu être relue. Relancez Coulisses si le problème "
                "reste."
            ) from exc

    def start(
        self,
        *,
        space_id: int | None,
        attendee_ids: list[int],
        unnamed_attendees: int | None,
        device_index: int | None,
        project_id: int | None = None,
        extra_device_indexes: list[int] | None = None,
        system: bool = False,
    ) -> RecordingState:
        """`extra_device_indexes`: microphones added, recording at the same time (often the
        iPhone through Continuity, ADR 0031, 0033), each into a file of its own. `system`:
        the computer's sound too, for a meeting online or hybrid (ADR 0032)."""
        with self._lock:
            if self._current is not None:
                raise RecordingError("Un enregistrement est déjà en cours.")
            # Chosen from a list read a moment ago: found again by name in the list as it
            # is now (a device that came back has another number). Two microphones of the
            # very same name cannot be told apart: the first one listed is taken.
            before = {d.index: d.name for d in self._devices()}
            asked = extra_device_indexes or []
            if len(set(asked)) != len(asked) or device_index in asked:
                raise RecordingError("Un même micro ne peut être choisi qu'une fois.")
            self._fresh()
            devices = self._devices()

            def find(index: int) -> InputDevice | None:
                name = before.get(index)
                return next((d for d in devices if d.name == name), None)

            if device_index is None:
                chosen = next((d for d in devices if d.default), devices[0] if devices else None)
            else:
                chosen = find(device_index)
            if chosen is None:
                raise RecordingError(
                    "Aucun micro trouvé : branchez-en un, ou choisissez-en un autre."
                )
            added: list[InputDevice] = []
            for index in asked:
                found = find(index)
                if found is None:
                    name = before.get(index)
                    raise RecordingError(
                        (f"Le micro « {name} »" if name else "Un micro choisi")
                        + " n'est plus là : s'il s'agit d'un iPhone, est-il encore près du "
                        "Mac, déverrouillé ?"
                    )
                if found.name in {chosen.name, *(d.name for d in added)}:
                    raise RecordingError("Un même micro ne peut être choisi qu'une fois.")
                added.append(found)
            flags = _Flags()
            # The microphones are opened and started before the session is made: one that
            # refuses leaves nothing behind (their first blocks wait in their queues).
            opened: list[_Opened] = []
            try:
                channels = min(chosen.channels, MAX_CHANNELS)
                blocks: queue.Queue[Block | None] = queue.Queue()
                if system:
                    heard_system: queue.Queue[Block | None] = queue.Queue()

                    def heard_both(block: NDArray[np.float32], lost: bool) -> None:
                        # One block, cut in two: the same instant on both files.
                        paused = flags.paused
                        blocks.put((block[:, :channels], lost, paused))
                        heard_system.put((block[:, channels:], lost, paused))

                    stream = self._open(
                        chosen,
                        lambda: self._system_stream_factory(chosen.name, channels, heard_both),
                    )
                    opened.append(
                        _Opened(sessions.REFERENCE_SOURCE_ID, chosen.name, channels, stream, blocks)
                    )
                    opened.append(
                        _Opened(
                            sessions.SYSTEM_SOURCE_ID,
                            sessions.SYSTEM_DEVICE,
                            1,
                            _Shared(),
                            heard_system,
                        )
                    )
                else:
                    stream = self._open(
                        chosen,
                        lambda: self._stream_factory(chosen.index, channels, _heard(blocks, flags)),
                    )
                    opened.append(
                        _Opened(sessions.REFERENCE_SOURCE_ID, chosen.name, channels, stream, blocks)
                    )
                for position, other in enumerate(added):
                    opened.append(self._open_added(position, other, flags))
            except RecordingError:
                for made in opened:
                    _close_quietly(made.stream)
                raise
            try:
                session_id, path = sessions.start_capture(
                    self.data,
                    space_id=space_id,
                    project_id=project_id,
                    attendee_ids=attendee_ids,
                    unnamed_attendees=unnamed_attendees,
                    device=chosen.name,
                    sample_rate=SAMPLE_RATE,
                    channels=opened[0].channels,
                    extra=[
                        (o.device, o.channels)
                        for o in opened
                        if sessions.is_extra_microphone(o.source_id)
                    ],
                    system=system,
                )
            except Exception:
                for made in opened:
                    _close_quietly(made.stream)
                raise
            tracks: list[_Track] = []
            for made in opened:
                target = path.with_name(sessions.capture_file(made.source_id))
                try:
                    writer = wav.WavWriter(
                        target, SAMPLE_RATE, made.channels, max_data_bytes=self._max_data_bytes
                    )
                except Exception as exc:
                    for each in opened:
                        _close_quietly(each.stream)
                    for track in tracks:
                        try:
                            track.writer.close()
                        except Exception:  # what it holds is a header: logged, not hidden
                            log.exception("closing %s", track.writer.path)
                    for each in opened:
                        sessions.close_empty_capture(
                            self.data, session_id, reason=str(exc), source_id=each.source_id
                        )
                    raise RecordingError(
                        f"Le fichier de l'enregistrement n'a pas pu être créé : {exc}"
                    ) from exc
                tracks.append(
                    _Track(
                        source_id=made.source_id,
                        device=made.device,
                        channels=made.channels,
                        writer=writer,
                        stream=made.stream,
                        blocks=made.blocks,
                        last_block_at=self._clock(),
                    )
                )
            recording = _Recording(session_id=session_id, flags=flags, tracks=tracks)
            for track in tracks:
                track.writer_thread = threading.Thread(
                    target=self._write,
                    args=(recording, track),
                    name=f"capture-writer-{track.source_id}",
                    daemon=True,
                )
                track.writer_thread.start()
            self.keep_awake.hold()
            self._current = recording
            return self._state(recording)

    def _open_added(self, position: int, device: InputDevice, flags: _Flags) -> _Opened:
        channels = min(device.channels, MAX_CHANNELS)
        blocks: queue.Queue[Block | None] = queue.Queue()
        stream = self._open(
            device,
            lambda: self._stream_factory(device.index, channels, _heard(blocks, flags)),
        )
        return _Opened(sessions.extra_source_id(position), device.name, channels, stream, blocks)

    def _open(self, device: InputDevice, make: Callable[[], InputStream]) -> InputStream:
        failure: Exception | None = None
        for attempt in range(OPEN_TRIES):
            if attempt:
                time.sleep(self._retry_wait_s)  # waking up (the iPhone): tried again
            try:
                stream = make()
            # PortAudio raises plain exceptions: each kept, the last raised below.
            except Exception as exc:  # noqa: BLE001
                failure = exc
                log.warning("opening %s (try %d): %s", device.name, attempt + 1, exc)
                continue
            try:
                stream.start()
            except system_audio.SystemAudioError as exc:
                # Permission, compiler, microphone's rate: trying again will not help.
                raise RecordingError(str(exc)) from exc
            except Exception as exc:  # noqa: BLE001
                _close_quietly(stream)
                failure = exc
                log.warning("starting %s (try %d): %s", device.name, attempt + 1, exc)
                continue
            return stream
        hint = (
            " Gardez l'iPhone déverrouillé près du Mac, Wi-Fi et Bluetooth activés sur les deux, "
            "même compte Apple, et vérifiez que son micro n'est pas pris (appel, autre app)."
            if "iphone" in device.name.lower()
            else " Sur macOS, l'accès au micro se donne dans Réglages Système, Confidentialité "
            "et sécurité, Micro, à l'application qui lance Coulisses."
        )
        raise RecordingError(f"Le micro « {device.name} » n'a pas pu s'ouvrir.{hint}") from failure

    def _write(self, recording: _Recording, track: _Track) -> None:
        """Drains the blocks from one microphone: levels always, audio unless paused. A
        failure to write stops writing that file, keeps what is there and says why (P8);
        the other microphone goes on."""
        while (item := track.blocks.get()) is not None:
            block, lost, paused = item
            peak = float(np.max(np.abs(block))) if block.size else 0.0
            rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
            now = self._clock()
            track.last_block_at = now
            track.dropouts += int(lost)
            track.levels = Levels(peak_db=_db(peak), rms_db=_db(rms))
            if track.levels.peak_db >= CLIP_DB:
                track.clipped_at = now
            if track.levels.rms_db < LOW_DB:
                track.quiet_since = track.quiet_since or now
            else:
                track.quiet_since = None
            if paused or track.error is not None:
                continue
            track.loudest = max(track.loudest, peak)
            try:
                track.writer.write(block)
            except wav.WavFullError as exc:
                track.error = (
                    f"L'enregistrement est arrêté : {exc}."
                    if track.source_id == sessions.REFERENCE_SOURCE_ID
                    else f"Le son de l'ordinateur n'est plus enregistré : {exc}."
                    if track.source_id == sessions.SYSTEM_SOURCE_ID
                    else f"Ce micro n'enregistre plus : {exc}."
                )
            except Exception as exc:  # disk full…: written so far is kept
                track.error = (
                    f"L'écriture sur le disque a échoué : {exc}. Ce qui précède est gardé."
                )
                log.exception("capture of %s (%s)", recording.session_id, track.source_id)

    def _alerts(self, track: _Track, paused: bool) -> tuple[bool, bool, str | None]:
        """(too quiet, clipping, error) of one microphone."""
        now = self._clock()
        too_quiet = (
            not paused and track.quiet_since is not None and now - track.quiet_since >= LOW_AFTER_S
        )
        clipping = track.clipped_at is not None and now - track.clipped_at <= CLIP_SHOWN_S
        # The computer's sound comes with the microphone: when they stop, the microphone
        # says it.
        error = track.error or (
            "Le micro ne donne plus de son depuis quelques secondes : est-il débranché ? "
            "Ce qui est enregistré est gardé."
            if now - track.last_block_at > SILENT_STREAM_S
            and track.source_id != sessions.SYSTEM_SOURCE_ID
            else None
        )
        return too_quiet, clipping, error

    def _state(self, recording: _Recording) -> RecordingState:
        main = recording.main
        paused = recording.flags.paused
        too_quiet, clipping, error = self._alerts(main, paused)

        def state_of(other: _Track) -> TrackState:
            quiet2, clip2, error2 = self._alerts(other, paused)
            return TrackState(
                device=other.device,
                levels=other.levels,
                too_quiet=quiet2,
                clipping=clip2,
                dropouts=other.dropouts,
                error=error2,
            )

        return RecordingState(
            session_id=recording.session_id,
            state="paused" if paused else "recording",
            elapsed_s=main.writer.frames / SAMPLE_RATE,
            device=main.device,
            channels=main.channels,
            levels=main.levels,
            too_quiet=too_quiet,
            clipping=clipping,
            dropouts=main.dropouts,
            markers=list(recording.markers),
            notes=list(recording.notes),
            error=error,
            extra=[
                state_of(t) for t in recording.tracks if sessions.is_extra_microphone(t.source_id)
            ],
            system=next(
                (state_of(t) for t in recording.tracks if t.source_id == sessions.SYSTEM_SOURCE_ID),
                None,
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
            elapsed = recording.main.writer.frames / SAMPLE_RATE
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
            elapsed = recording.main.writer.frames / SAMPLE_RATE
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
        """Stop, close the files, describe them; queue the processing unless on battery.
        Whatever the microphones do, the session is closed with what is on disk. A second
        track (a microphone, the computer's sound) that could not be read back is said and
        kept; it never stops the main recording from being closed (ADR 0031, 0032)."""
        with self._lock:
            recording = self._current
            if recording is None:
                raise RecordingError("Aucun enregistrement en cours.")
            self._current = None
            self._closing = True
        said: list[str] = []
        try:
            for track in recording.tracks:
                if (problem := _close_quietly(track.stream)) is not None:
                    said.append(f"{track.device} : {problem}")
                track.blocks.put(None)
        finally:
            with self._lock:
                self._closing = False
        for track in recording.tracks:
            if track.writer_thread is not None:
                track.writer_thread.join()
        try:
            for track in recording.tracks:
                try:
                    track.writer.close()
                # Its last header write, whatever failed: `repair` below makes it true.
                except Exception:
                    log.exception("closing %s", track.writer.path)
        finally:
            self.keep_awake.release()
        # From what is on disk, whatever the writers managed: the headers are made true.
        # The main recording first: a second microphone never keeps it from being closed.
        main = recording.main
        main_error: Exception | None = None
        frames = 0
        try:
            frames = wav.repair(main.writer.path)
            sessions.finish_capture(self.data, recording.session_id, frames=frames)
        except Exception as exc:
            log.exception("closing the recording of %s", recording.session_id)
            sessions.close_empty_capture(
                self.data, recording.session_id, reason=str(exc), unreadable=True
            )
            main_error = exc
        problems = [
            problem
            for track in recording.tracks[1:]
            if (problem := self._close_extra(recording.session_id, track)) is not None
        ]
        system = next(
            (t for t in recording.tracks if t.source_id == sessions.SYSTEM_SOURCE_ID), None
        )
        if system is not None:
            if system.writer.frames and system.loudest < mixing.SILENT_PEAK:
                problems.append(SYSTEM_SILENT)
            # To be heard on the session's page at once, before the processing gets to it.
            mixing.prepare_in_background(self.data, recording.session_id)
        second_problem = " ".join(problems) or None
        if main_error is not None:
            raise RecordingError(
                f"L'enregistrement est arrêté, mais son fichier n'a pas pu être relu : "
                f"{main_error}. Il reste dans le dossier de la séance."
            ) from main_error
        battery = self._battery()
        processing = frames > 0 and not battery
        if processing:
            sessions.start_processing(self.data, recording.session_id, profile=profile)
        if said:
            log.warning(
                "recording %s stopped, microphones said: %s", recording.session_id, "; ".join(said)
            )
        return StopResult(
            session_id=recording.session_id,
            duration_s=frames / SAMPLE_RATE,
            processing=processing,
            on_battery=battery,
            second_problem=second_problem,
        )

    def _close_extra(self, session_id: str, track: _Track) -> str | None:
        """A second track's file, described; what went wrong, said to the user (never
        raised: the main recording is already closed)."""
        try:
            kept = wav.repair(track.writer.path)
            sessions.finish_capture(self.data, session_id, frames=kept, source_id=track.source_id)
            return None
        except Exception as exc:
            log.exception("closing the track %s of %s", track.source_id, session_id)
            try:
                sessions.close_empty_capture(
                    self.data,
                    session_id,
                    reason=str(exc),
                    unreadable=True,
                    source_id=track.source_id,
                )
            except Exception:  # the database itself: the next start repairs it (logged)
                log.exception("marking the track %s of %s", track.source_id, session_id)
            what = (
                "La piste du son de l'ordinateur"
                if track.source_id == sessions.SYSTEM_SOURCE_ID
                else f"La piste du micro « {track.device} »"
            )
            return (
                f"{what} n'a pas pu être relue : {exc}. Son fichier reste dans le dossier de "
                "la séance ; l'enregistrement principal est complet."
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
    for session_id, source_id in sessions.interrupted_captures(data):
        path = data.sources_dir(session_id) / sessions.capture_file(source_id)
        second = source_id != sessions.REFERENCE_SOURCE_ID
        what = (
            "Son de l'ordinateur d'un enregistrement interrompu"
            if source_id == sessions.SYSTEM_SOURCE_ID
            else "Micro ajouté d'un enregistrement interrompu"
            if second
            else "Enregistrement interrompu"
        )
        try:
            frames = wav.repair(path)
            sessions.finish_capture(
                data, session_id, frames=frames, state="recovered", source_id=source_id
            )
        except Exception as exc:
            log.exception("recovering the recording of %s (%s)", session_id, source_id)
            sessions.close_empty_capture(
                data, session_id, reason=str(exc), unreadable=True, source_id=source_id
            )
            told.append(f"{what} illisible ({session_id}) : {exc}")
            continue
        minutes = frames / SAMPLE_RATE / 60
        told.append(
            f"{what} récupéré ({session_id}, {minutes:.0f} min)"
            + ("." if second else " : ouvrez la séance pour lancer son traitement.")
        )
    return told
