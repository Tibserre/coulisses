"""What this Mac has, for the advice of the Rédaction tab (lot 11g of the plan)."""

from __future__ import annotations

import os


def memory_gb() -> float | None:
    """The Mac's memory in GB (1024³ bytes, as macOS says it); None if it cannot be read
    (then said as unknown, never guessed)."""
    try:
        pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        return None
    # sysconf says -1 when it does not know, without raising.
    return pages * size / 1024**3 if pages > 0 and size > 0 else None
