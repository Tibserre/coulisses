"""Writes that must be on the disk before what follows them (a file removed, a name given):
macOS's `fsync` leaves them in the drive's cache; `F_FULLFSYNC` does not."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


def sync_file(path: Path) -> None:
    """The content of `path` on the disk itself."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        full = getattr(fcntl, "F_FULLFSYNC", None)
        if full is not None:
            fcntl.fcntl(descriptor, full)
        else:
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sync_folder(folder: Path) -> None:
    """The names in `folder` (a file renamed, removed) on the disk itself."""
    sync_file(folder)
