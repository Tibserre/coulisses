"""What an imported file holds: its first audio track, read by ffprobe (no decoding)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel


class UnreadableAudioError(ValueError):
    """The file has no audio track ffmpeg can read. The message is shown to the user."""


@dataclass(frozen=True)
class AudioInfo:
    duration_s: float | None
    sample_rate: int | None
    channels: int | None
    codec: str | None


def probe(path: Path) -> AudioInfo:
    try:
        done = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-select_streams",
                "a:0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UnreadableAudioError(
            "ffprobe est introuvable : installez ffmpeg (brew install ffmpeg)."
        ) from exc
    if done.returncode != 0:
        detail = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "erreur inconnue"
        raise UnreadableAudioError(f"Ce fichier n'est pas lisible par ffmpeg ({detail}).")
    info = _Probe.model_validate_json(done.stdout or "{}")
    if not info.streams:
        raise UnreadableAudioError("Ce fichier ne contient aucune piste audio.")
    stream = info.streams[0]
    duration = stream.duration or (info.format.duration if info.format else None)
    return AudioInfo(
        duration_s=float(duration) if duration else None,
        sample_rate=int(stream.sample_rate) if stream.sample_rate else None,
        channels=stream.channels,
        codec=stream.codec_name,
    )


class _Stream(BaseModel):
    codec_name: str | None = None
    sample_rate: str | None = None
    channels: int | None = None
    duration: str | None = None


class _Format(BaseModel):
    duration: str | None = None


class _Probe(BaseModel):
    """The part of ffprobe's JSON we read; the rest is ignored."""

    streams: list[_Stream] = []
    format: _Format | None = None
