"""A WAV file written as it is recorded (ADR 0005): PCM 24 bits, the header kept true.

The header gives the size of the audio. It is rewritten, and the file forced to disk, at
least every second: after a crash, at most that much is missing from what the header
says, and `repair` makes the header match what is on disk (spec §7.2: a few seconds at
most are lost).
"""

from __future__ import annotations

import hashlib
import os
import struct
import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

HEADER_BYTES = 44
MAX_DATA_BYTES = 0xFFFF_FFFF - 36
"""A WAV file holds at most 4 GiB of audio: about 8 h in mono, 4 h in stereo, at 24 bits
and 48 kHz."""
SAMPLE_BYTES = 3  # PCM 24 bits: raw, with room above the noise floor of a microphone
_FULL_SCALE = 2**23


def _header(rate: int, channels: int, data_bytes: int) -> bytes:
    block = channels * SAMPLE_BYTES
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", 36 + data_bytes),
            b"WAVE",
            b"fmt ",
            struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * block, block, 8 * SAMPLE_BYTES),
            b"data",
            struct.pack("<I", data_bytes),
        ]
    )


def to_pcm24(frames: NDArray[np.float32]) -> bytes:
    """Float samples (-1 to 1, one row per frame, one column per channel), as
    interleaved little-endian 24 bits."""
    scaled = np.clip(frames, -1.0, 1.0 - 1.0 / _FULL_SCALE) * _FULL_SCALE
    as_int = np.round(scaled).astype("<i4").reshape(-1)
    return as_int.view(np.uint8).reshape(-1, 4)[:, :SAMPLE_BYTES].tobytes()


class WavFullError(OSError):
    """The file reached the size a WAV can hold: what is written is kept, nothing more."""


class WavWriter:
    """Appends audio to a new file; the header follows, at least every `sync_s` seconds."""

    def __init__(
        self,
        path: Path,
        rate: int,
        channels: int,
        *,
        sync_s: float = 1.0,
        max_data_bytes: int = MAX_DATA_BYTES,
    ) -> None:
        self.path = path
        self.max_data_bytes = max_data_bytes
        self.rate = rate
        self.channels = channels
        self.sync_s = sync_s
        self._file = path.open("xb")
        self._file.write(_header(rate, channels, 0))
        self._data_bytes = 0
        self._last_sync = time.monotonic()
        self._sync()

    @property
    def frames(self) -> int:
        return self._data_bytes // (self.channels * SAMPLE_BYTES)

    def write(self, frames: NDArray[np.float32]) -> None:
        payload = to_pcm24(frames)
        if self._data_bytes + len(payload) > self.max_data_bytes:
            self._sync()
            raise WavFullError(
                "l'enregistrement a atteint la taille maximale d'un fichier WAV (4 Go, environ "
                "8 h en mono) : il s'arrête ici, tout ce qui précède est gardé"
            )
        self._file.write(payload)
        self._data_bytes += len(payload)
        if time.monotonic() - self._last_sync >= self.sync_s:
            self._sync()

    def _sync(self) -> None:
        self._file.seek(0)
        self._file.write(_header(self.rate, self.channels, self._data_bytes))
        self._file.seek(0, os.SEEK_END)
        self._file.flush()
        os.fsync(self._file.fileno())
        self._last_sync = time.monotonic()

    def close(self) -> None:
        if self._file.closed:
            return
        try:
            self._sync()
        finally:
            # Closed even if the last header write fails: nothing left to land after it.
            self._file.close()


def repair(path: Path) -> int:
    """Make the header of an interrupted recording match the audio on disk (a partial last
    frame is left out of it, never cut from the file). Returns the number of frames."""
    with path.open("r+b") as f:
        head = f.read(HEADER_BYTES)
        if len(head) < HEADER_BYTES or head[:4] != b"RIFF" or head[36:40] != b"data":
            raise ValueError(f"{path.name} n'est pas un enregistrement de Coulisses lisible.")
        channels, rate = struct.unpack("<HI", head[22:28])
        block = channels * SAMPLE_BYTES
        size = f.seek(0, os.SEEK_END)
        # Beyond what a WAV can say, the header gives the most it can (never a crash).
        data_bytes = min(size - HEADER_BYTES, MAX_DATA_BYTES) // block * block
        f.seek(0)
        f.write(_header(rate, channels, data_bytes))
        f.flush()
        os.fsync(f.fileno())
    return data_bytes // block


def layout(path: Path) -> tuple[int, int, int]:
    """(rate, channels, bytes of samples its header declares) of a WAV written by
    Coulisses; ValueError if it is not one."""
    with path.open("rb") as f:
        head = f.read(HEADER_BYTES)
    if len(head) < HEADER_BYTES or head[:4] != b"RIFF" or head[36:40] != b"data":
        raise ValueError(f"{path.name} n'est pas un enregistrement de Coulisses lisible.")
    channels, rate = struct.unpack("<HI", head[22:28])
    (data_bytes,) = struct.unpack("<I", head[40:44])
    return rate, channels, data_bytes


def pcm_sha256(path: Path) -> str:
    """The fingerprint of the samples of a WAV written by Coulisses (what its header
    declares, interleaved little-endian 24 bits): the same as that of the samples decoded
    from a lossless copy in another format (ADR 0046). ValueError if it is not one."""
    _, _, data_bytes = layout(path)
    digest = hashlib.sha256()
    with path.open("rb") as f:
        f.seek(HEADER_BYTES)
        left = data_bytes
        while left > 0 and (chunk := f.read(min(left, 1 << 20))):
            digest.update(chunk)
            left -= len(chunk)
    if left:
        raise ValueError(f"{path.name} est plus court que ce que son en-tête annonce.")
    return digest.hexdigest()


def header(rate: int, channels: int, data_bytes: int) -> bytes:
    """The 44-byte header Coulisses writes (PCM 24 bits), for `data_bytes` of samples."""
    return _header(rate, channels, data_bytes)
