"""When ffmpeg cannot convert, the tracks stay in WAV and the log says why (ADR 0046): FLAC
to write, and 24-bit PCM to read it back and prove it. A fake ffmpeg lists what it can do."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from coulisses_app import lossless

CODECS = (" A....D flac   FLAC (Free Lossless Audio Codec)", " A....D pcm_s24le   PCM 24-bit")
FULL = {
    "-encoders": CODECS,
    "-muxers": ("  E  flac   raw FLAC", "  E  s24le  PCM signed 24-bit little-endian"),
    "-decoders": CODECS,
}


def fake_ffmpeg(folder: Path, listings: dict[str, tuple[str, ...]]) -> None:
    script = folder / "ffmpeg"
    cases = "".join(
        f"  {listing}) printf '%s\\n' 'Header:' ' ------' {' '.join(map(repr, lines))} ;;\n"
        for listing, lines in listings.items()
    )
    script.write_text(f'#!/bin/sh\ncase "$2" in\n{cases}esac\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


@pytest.mark.parametrize(
    ("listing", "kept", "said"),
    [
        ("-encoders", 1, "l'encodeur FLAC"),
        ("-encoders", 0, "l'encodeur PCM 24 bits"),
        ("-muxers", 1, "le format FLAC"),
        ("-muxers", 0, "le format PCM 24 bits"),
        ("-decoders", 1, "le décodeur FLAC"),
        ("-decoders", 0, "le décodeur PCM 24 bits"),
    ],
)
def test_an_ffmpeg_that_cannot_prove_a_flac_keeps_the_tracks_in_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing: str, kept: int, said: str
) -> None:
    fake_ffmpeg(tmp_path, FULL | {listing: (FULL[listing][kept],)})
    monkeypatch.setenv("PATH", str(tmp_path))
    assert lossless.available() == f"le ffmpeg de cette app n'a pas {said}"


def test_a_full_ffmpeg_converts_and_no_ffmpeg_is_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert lossless.available() == "ffmpeg est introuvable"
    fake_ffmpeg(tmp_path, FULL)
    assert lossless.available() is None
