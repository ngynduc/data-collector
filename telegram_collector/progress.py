"""Progress + ETA tracking for the live log line."""

from __future__ import annotations

import time


class Progress:
    """Lightweight rate/ETA estimator. No rich progress bar dependency."""

    def __init__(self, total: int | None = None) -> None:
        self.total = total
        self.count = 0
        self.start = time.monotonic()

    def update_total(self, total: int | None) -> None:
        self.total = total

    def advance(self, n: int = 1) -> None:
        self.count += n

    def eta_str(self) -> str:
        elapsed = time.monotonic() - self.start
        if self.count <= 0:
            return "—"
        rate = self.count / elapsed if elapsed > 0 else 0
        if not self.total or self.count >= self.total:
            return "done"
        remaining = self.total - self.count
        if rate <= 0:
            return "?"
        secs = remaining / rate
        return _human_duration(secs)

    def rate_str(self) -> str:
        elapsed = time.monotonic() - self.start
        if elapsed <= 0:
            return "0/s"
        return f"{self.count / elapsed:.1f}/s"

    def progress_str(self) -> str:
        if not self.total:
            return f"{self.count}"
        pct = (self.count / self.total) * 100 if self.total else 0
        return f"{self.count}/{self.total} ({pct:.1f}%)"


def _human_duration(secs: float) -> str:
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m{secs % 60}s"
    h, rem = divmod(secs, 3600)
    m = rem // 60
    return f"{h}h{m}m"
