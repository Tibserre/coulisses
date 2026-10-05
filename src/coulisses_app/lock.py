"""One application per data folder: a second one would process the same jobs twice."""

from __future__ import annotations

import fcntl
import os
from typing import IO

from coulisses_app.paths import DataDir

LOCK_FILE = ".coulisses-app.lock"


class AlreadyRunningError(RuntimeError):
    """Another Coulisses already uses this data folder. The message is shown to the user."""


def hold_data_lock(data: DataDir) -> IO[str]:
    """Take the folder's lock for the life of the process (released by the system when it
    ends, even after a crash). Keep the returned file open."""
    data.root.mkdir(parents=True, exist_ok=True)
    handle = (data.root / LOCK_FILE).open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        owner = handle.read().strip() or "inconnu"
        handle.close()
        raise AlreadyRunningError(
            f"Coulisses tourne déjà sur {data.root} (processus {owner}). "
            "Utilisez la fenêtre déjà ouverte, ou arrêtez l'autre instance."
        ) from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle
