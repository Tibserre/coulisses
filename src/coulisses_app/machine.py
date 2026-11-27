"""What this Mac has, for the advice of the Rédaction tab (lot 11g of the plan) and the
processing times (ADR 0095)."""

from __future__ import annotations

import os
import platform
import subprocess


def memory_gb() -> float | None:
    """The Mac's memory in GB (1024³ bytes, as macOS says it); None if it cannot be read
    (then said as unknown, never guessed)."""
    try:
        pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        return None
    # sysconf says -1 when it does not know, without raising.
    return pages * size / 1024**3 if pages > 0 and size > 0 else None


def _sysctl(key: str) -> str | None:
    try:
        done = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def _count(key: str) -> int | None:
    value = _sysctl(key)
    return int(value) if value is not None and value.isdigit() else None


def describe() -> dict[str, object]:
    """This Mac as macOS says it, for the processing times (ADR 0095): what is unknown is
    None, never guessed."""
    return {
        "chip": _sysctl("machdep.cpu.brand_string"),
        "cores": _count("hw.physicalcpu"),
        "performance_cores": _count("hw.perflevel0.physicalcpu"),
        "efficiency_cores": _count("hw.perflevel1.physicalcpu"),
        "memory_gb": memory_gb(),
        "macos": platform.mac_ver()[0] or None,
    }
