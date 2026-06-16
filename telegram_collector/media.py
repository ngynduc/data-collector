"""Media download manager: bounded concurrency, dedup, FloodWait-safe."""

from __future__ import annotations

import asyncio
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .logging_setup import get_logger
from .ratelimit import RateLimiter, handle_floodwait
from .serializers import media_subdir
from .state import ProgressState

log = get_logger("media")


class MediaDownloader:
    def __init__(
        self,
        client: TelegramClient,
        media_root: Path,
        state: ProgressState,
        rate_limiter: RateLimiter,
        concurrency: int,
    ) -> None:
        self.client = client
        self.media_root = media_root
        self.state = state
        self.rate = rate_limiter
        self._sem = asyncio.Semaphore(concurrency)
        self.downloaded = 0
        self.skipped = 0
        self.failed = 0

    def _target_dir(self, media_meta: dict) -> Path:
        subdir = media_subdir(media_meta["kind"])
        path = self.media_root / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def download(self, message, media_meta: dict) -> str | None:
        """Download one media item. Returns local path or None if skipped/failed."""
        key = self.state.media_key(media_meta)
        if self.state.is_media_downloaded(key):
            self.skipped += 1
            return None

        async with self._sem:
            target_dir = self._target_dir(media_meta)
            await self.rate.wait()
            try:
                written = await self.client.download_media(message, file=str(target_dir))
            except FloodWaitError as exc:
                ok = await handle_floodwait(exc, context=f"media {media_meta.get('file_name')}")
                if not ok:
                    self.failed += 1
                    return None
                written = await self.client.download_media(message, file=str(target_dir))
            except Exception as exc:  # noqa: BLE001 — never abort a whole run for one file
                log.error("Failed media for msg %s in %s: %s", media_meta.get("message_id"), media_meta.get("chat_id"), exc)
                self.failed += 1
                return None

            if not written:
                # Telethon returns None when there is nothing to download.
                return None

            written_path = Path(written)
            try:
                size = written_path.stat().st_size
            except OSError:
                size = None
            self.state.mark_media_downloaded(key, str(written_path), size)
            self.downloaded += 1
            log.debug(
                "media saved msg=%s -> %s (%s bytes)",
                media_meta.get("message_id"), written_path.name, size,
            )
            return str(written_path)

    async def download_page(
        self, items: list[tuple[object, dict]]
    ) -> dict[int, str]:
        """Download media for a page of (message, media_meta) concurrently.

        Returns {message_id: local_path}.
        """
        results: dict[int, str] = {}
        if not items:
            return results

        async def _one(message, media_meta):
            path = await self.download(message, media_meta)
            if path:
                results[media_meta["message_id"]] = path

        await asyncio.gather(*(_one(m, mm) for m, mm in items))
        return results
