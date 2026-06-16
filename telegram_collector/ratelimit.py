"""Small async rate limiter + FloodWait helpers."""

from __future__ import annotations

import asyncio
import time

from telethon.errors import FloodWaitError

from .logging_setup import get_logger

log = get_logger("rate")


class RateLimiter:
    """Sleeps a configurable delay between calls. Call .wait() before each unit of work."""

    def __init__(self, delay: float) -> None:
        self.delay = max(0.0, delay)
        self._last = 0.0

    async def wait(self) -> None:
        if self.delay <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self._last = time.monotonic()


async def handle_floodwait(
    exc: FloodWaitError,
    *,
    context: str,
    max_wait: int = 3600,
) -> bool:
    """Log a FloodWait and sleep it off. Returns False if the wait exceeds max_wait."""
    seconds = int(getattr(exc, "seconds", 0)) + 1
    if seconds > max_wait:
        log.warning(
            "FloodWait on %s is %ss (> max %ss). Skipping unit.",
            context, seconds - 1, max_wait,
        )
        return False
    log.warning("FloodWait on %s: sleeping %ss.", context, seconds - 1)
    await asyncio.sleep(seconds)
    return True
