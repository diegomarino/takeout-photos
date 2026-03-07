from __future__ import annotations

import time


class Timer:
    """Context manager for measuring elapsed time with smart formatting.

    Example:
        >>> with Timer() as t:
        ...     # ... do work ...
        ...     pass
        >>> print(f"Operation complete ({t.format_elapsed()})")
        Operation complete (5m 44s)
    """

    def __init__(self, name: str = ""):
        """Initialize timer.

        Args:
            name: Optional name for the timer (unused, for debugging)
        """
        self.name = name
        self.start_time: float | None = None
        self.elapsed: float | None = None

    def __enter__(self) -> Timer:
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, *args) -> None:
        """Stop timing and compute elapsed."""
        if self.start_time is not None:
            self.elapsed = time.time() - self.start_time

    def format_elapsed(self) -> str:
        """Format elapsed time intelligently as Xh Ym Zs.

        Returns:
            Formatted time string omitting zero hours/minutes

        Examples:
            - 3 seconds → "3s"
            - 5 minutes 44 seconds → "5m 44s"
            - 1 hour 14 minutes 12 seconds → "1h 14m 12s"
        """
        if self.elapsed is None:
            return "0s"

        total_seconds = int(self.elapsed)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or hours > 0:  # Show minutes if hours exist
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return " ".join(parts)
