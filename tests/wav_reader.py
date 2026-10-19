"""Reads the WAV files the app writes, for the tests, with Python's own `wave` module: a
reader independent of the app's writer (`wav.py`), without any native library."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class WavInfo:
    samplerate: int
    channels: int
    bits: int
    frames: int


def info(path: Path) -> WavInfo:
    with wave.open(str(path), "rb") as stream:
        return WavInfo(
            stream.getframerate(),
            stream.getnchannels(),
            8 * stream.getsampwidth(),
            stream.getnframes(),
        )


def read(path: Path, always_2d: bool = False) -> NDArray[np.float64]:
    """The samples in [-1, 1), one column per channel; a mono file as one dimension unless
    `always_2d`."""
    with wave.open(str(path), "rb") as stream:
        width, channels = stream.getsampwidth(), stream.getnchannels()
        raw = np.frombuffer(stream.readframes(stream.getnframes()), dtype=np.uint8)
    if width == 3:  # little-endian 24 bits, sign-extended into 32
        padded = np.zeros((raw.size // 3, 4), dtype=np.uint8)
        padded[:, 1:] = raw.reshape(-1, 3)
        values = padded.view("<i4").reshape(-1).astype(np.float64) / 2**31
    elif width == 2:
        values = raw.view("<i2").astype(np.float64) / 2**15
    else:
        raise ValueError(f"{path.name} : {8 * width} bits, non lu par ce lecteur de test")
    samples = values.reshape(-1, channels)
    return samples if always_2d or channels > 1 else samples[:, 0]
