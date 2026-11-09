"""The real program, on this Mac's default microphone: a recording's rate the microphone
cannot run at (as AirPods in hands-free mode cannot run at 48 kHz) is converted, both
tracks together. Run by hand: `uv run pytest -m materiel`."""

from __future__ import annotations

import time

import numpy as np
import pytest
from numpy.typing import NDArray

from coulisses_app import capture, system_audio

pytestmark = pytest.mark.materiel

UNUSUAL_RATE = 32_000
"""Run by no Mac microphone: the program has to convert, up or down."""


def test_a_microphone_at_another_rate_is_converted_to_the_recordings() -> None:
    microphone = next(d for d in capture.input_devices() if d.default)
    frames: list[int] = []

    def heard(block: NDArray[np.float32], _lost: bool) -> None:
        assert block.shape[1] == 2  # the microphone, then the computer's sound
        frames.append(len(block))

    stream = system_audio.HelperStream(microphone.name, 1, heard, rate=UNUSUAL_RATE)
    stream.start()
    started = time.monotonic()
    time.sleep(3)
    stream.stop()
    elapsed = time.monotonic() - started
    # The blocks come at the recording's rate, within what the start and stop blur.
    assert sum(frames) / elapsed == pytest.approx(UNUSUAL_RATE, rel=0.1)
