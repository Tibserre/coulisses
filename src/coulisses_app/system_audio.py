"""The computer's sound, recorded with the microphone (ADR 0032).

Python cannot tap what macOS plays: a small Swift program does (`native/son-ordinateur/`).
Coulisses.app carries it built (ADR 0040); from the repository, it is built on this Mac
with Apple's own compiler the first time it is needed. It puts the
computer's sound beside the microphone in one stream on the microphone's clock, and hands
it over as raw samples on its standard output: the service writes them as it writes any
microphone (`capture.py`), into two files.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import struct
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO

import numpy as np
from numpy.typing import NDArray

from coulisses_app.bundle import Resources
from coulisses_app.spaces import SpaceError

log = logging.getLogger(__name__)

SOURCE_DIR = Path(__file__).resolve().parents[2] / "native" / "son-ordinateur"
BUILT = SOURCE_DIR / "build" / "coulisses-son-ordinateur"
READY_WITHIN_S = 15.0
"""Starting the tap and the microphone; macOS may ask for the permission meanwhile."""
STOP_WITHIN_S = 5.0
HEADER = struct.Struct("<II")
"""Before each block: its frames, and the frames lost just before it."""

_build_lock = threading.Lock()


OnBlock = Callable[[NDArray[np.float32], bool], None]


class SystemAudioError(SpaceError):
    """The computer's sound cannot be recorded; the message is shown to the user."""


class UnavailableError(SystemAudioError):
    """The program that taps it cannot be built here: trying again will not help."""


def _sources() -> list[Path]:
    return [SOURCE_DIR / "main.swift", SOURCE_DIR / "Info.plist"]


def _up_to_date() -> bool:
    if not BUILT.is_file():
        return False
    built = BUILT.stat().st_mtime
    return all(source.stat().st_mtime <= built for source in _sources())


def compile_program(output: Path, minimum_macos: str = "14.4") -> None:
    """Builds the program into `output` with Apple's compiler, for the repository and for
    Coulisses.app (`scripts/construire.py`, which gives its minimum macOS). Raises
    `UnavailableError`."""
    swiftc = shutil.which("swiftc")
    if swiftc is None:
        raise UnavailableError(
            "Pour enregistrer le son de l'ordinateur, Coulisses a besoin des outils de "
            "développement d'Apple. Installez-les une fois avec « xcode-select --install » "
            "dans le Terminal, puis réessayez."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        swiftc,
        "-O",
        "-swift-version",
        "5",
        "-target",
        f"arm64-apple-macosx{minimum_macos}",
        str(SOURCE_DIR / "main.swift"),
        "-o",
        str(output),
        # Its usage description, read by macOS when it asks for the permission.
        *("-Xlinker", "-sectcreate", "-Xlinker", "__TEXT", "-Xlinker", "__info_plist"),
        *("-Xlinker", str(SOURCE_DIR / "Info.plist")),
    ]
    log.info("building %s", output)
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        log.exception("building the system audio helper")
        raise UnavailableError(
            f"Le module qui capte le son de l'ordinateur n'a pas pu être préparé : {exc}"
        ) from exc
    if done.returncode != 0:
        log.error("swiftc failed:\n%s", done.stderr)
        output.unlink(missing_ok=True)
        raise UnavailableError(
            "Le module qui capte le son de l'ordinateur n'a pas pu être préparé "
            "(le détail est dans le journal du service)."
        )


def ensure_built(resources: Resources | None = None) -> Path:
    """The program: the .app's, or, from the repository, built again whenever its source
    changed (never anything written into the .app). Raises `UnavailableError`."""
    shipped = (resources or Resources.from_env()).system_audio_program
    if shipped is not None:
        if not shipped.is_file():
            raise UnavailableError(
                "Le module qui capte le son de l'ordinateur manque dans Coulisses : "
                "réinstallez-la depuis le DMG."
            )
        return shipped
    with _build_lock:
        if _up_to_date():
            return BUILT
        partial = BUILT.with_name(BUILT.name + ".partiel")
        partial.unlink(missing_ok=True)
        compile_program(partial)
        os.replace(partial, BUILT)
        return BUILT


_MESSAGES = {
    "micro_introuvable": "Le micro « {micro} » est introuvable pour l'enregistrer avec le son "
    "de l'ordinateur : est-il encore branché ?",
    "tap": "macOS a refusé de donner le son de l'ordinateur. Autorisez-le dans Réglages "
    "Système, Confidentialité et sécurité, Enregistrement de l'écran et de l'audio du "
    "système, à l'application qui lance Coulisses.",
    "frequence": "Le micro « {micro} » ne peut pas enregistrer en 48 kHz avec le son de "
    "l'ordinateur : choisissez le micro du Mac.",
}


def _message(code: str, micro: str) -> str:
    return _MESSAGES.get(
        code, "Le micro et le son de l'ordinateur n'ont pas pu être ouverts ensemble."
    ).format(micro=micro)


class HelperStream:
    """The microphone and the computer's sound, as one stream (`capture.InputStream`): each
    block holds the microphone's `channels`, then the computer's sound."""

    def __init__(
        self,
        microphone: str,
        channels: int,
        on_block: OnBlock,
        *,
        program: Path | None = None,
        rate: int = 48_000,
    ) -> None:
        self.microphone = microphone
        self.channels = channels
        self._on_block = on_block
        self._program = program
        self._rate = rate
        self._process: subprocess.Popen[bytes] | None = None
        self._ready = threading.Event()
        self._failure: str | None = None
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        program = self._program or ensure_built()
        self._process = subprocess.Popen(
            [
                str(program),
                "--micro",
                self.microphone,
                "--canaux",
                str(self.channels),
                "--frequence",
                str(self._rate),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self._process.stdout is not None and self._process.stderr is not None
        self._threads = [
            threading.Thread(
                target=self._listen,
                args=(self._process.stderr,),
                daemon=True,
                name="system-audio-events",
            ),
        ]
        self._threads[0].start()
        deadline = time.monotonic() + READY_WITHIN_S
        while not self._ready.wait(0.05):
            if self._failure is not None or self._process.poll() is not None:
                break
            if time.monotonic() > deadline:
                # No sound at all: macOS holds it back until the permission is given.
                log.error("system audio: no sound within %.0f s", READY_WITHIN_S)
                self._failure = _message("tap", self.microphone)
                break
        if not self._ready.is_set():
            self._end()
            # What it said, or that it said nothing before stopping (logged in full).
            raise SystemAudioError(self._failure or "Le son de l'ordinateur n'a pas démarré.")
        reader = threading.Thread(
            target=self._read,
            args=(self._process.stdout,),
            daemon=True,
            name="system-audio-reader",
        )
        reader.start()
        self._threads.append(reader)

    def _listen(self, stderr: IO[bytes]) -> None:
        for raw in stderr:
            try:
                event = json.loads(raw)
            except ValueError:
                log.warning("system audio said: %s", raw.decode(errors="replace").rstrip())
                continue
            kind = event.get("event")
            if kind == "ready":
                log.info("system audio ready: %s", event)
                self._ready.set()
            elif kind == "error":
                log.error("system audio failed: %s", event)
                self._failure = _message(str(event.get("code")), self.microphone)
            else:
                log.info("system audio: %s", event)

    def _read(self, stdout: IO[bytes]) -> None:
        """Each block: its frames and the frames lost just before it, then the samples."""
        width = self.channels + 1
        heard = 0
        while len(header := stdout.read(HEADER.size)) == HEADER.size:
            frames, lost = HEADER.unpack(header)
            if lost:
                # Where, in the recording's frames, and how much: for whoever looks later.
                log.warning(
                    "system audio: %d frames lost before stream frame %d (pauses included)",
                    lost,
                    heard,
                )
            heard += frames
            payload = stdout.read(frames * width * 4)
            usable = len(payload) // (width * 4) * width * 4
            if usable:
                block = np.frombuffer(payload[:usable], dtype="<f4").reshape(-1, width).copy()
                self._on_block(block, lost > 0)
            if usable < frames * width * 4:
                break  # it stopped in the middle of a block: what came is kept

    def _end(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()  # it stops, writes what it heard, and closes
            process.wait(timeout=STOP_WITHIN_S)
        except (OSError, subprocess.TimeoutExpired):
            log.warning("system audio did not stop by itself: terminated")
            process.terminate()
            try:
                process.wait(timeout=STOP_WITHIN_S)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        # It has ended: its pipes close, so the readers end too, once all it said is read.
        # Waited for in full: a block left behind would be lost to the files (P8).
        for thread in self._threads:
            thread.join()

    def stop(self) -> None:
        self._end()

    def close(self) -> None:
        self._end()
