"""Collection orchestrator: account, dialogs, messages (JSONL), media, users."""

from __future__ import annotations

from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .config import Settings
from .logging_setup import get_logger
from .media import MediaDownloader
from .progress import Progress
from .ratelimit import RateLimiter, handle_floodwait
from .serializers import serialize_account, serialize_dialog, serialize_message
from .state import ProgressState
from .storage import append_jsonl, truncate_jsonl_after, write_json
from .users import UserIndex

log = get_logger("collector")


class Collector:
    def __init__(
        self,
        client: TelegramClient,
        settings: Settings,
        state: ProgressState,
        user_index: UserIndex,
        downloader: MediaDownloader | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.state = state
        self.users = user_index
        self.downloader = downloader
        self.export_dir = settings.export_dir
        self.messages_dir = export_messages_dir(settings.export_dir)
        self.dialog_rate = RateLimiter(settings.rate_dialog_delay)
        self.page_rate = RateLimiter(settings.rate_page_delay)

    # -- account -------------------------------------------------------------

    async def export_account(self) -> dict:
        me = await self.client.get_me()
        data = serialize_account(me)
        write_json(self.export_dir / "account.json", data)
        self.users.add(me)
        log.info("Wrote account.json for %s (id=%s)", data.get("username") or data.get("phone"), data["id"])
        return data

    # -- dialogs -------------------------------------------------------------

    async def collect_dialogs(self) -> list[tuple[dict, object]]:
        """Crawl all dialogs, write chats.json, return [(meta, entity), ...]."""
        log.info("Listing dialogs (this may take a moment)...")
        results: list[tuple[dict, object]] = []
        async for dialog in self.client.iter_dialogs():
            meta = serialize_dialog(dialog)
            results.append((meta, dialog.entity))
            self.users.add(dialog.entity)

        metas = [m for m, _ in results]
        write_json(self.export_dir / "chats.json", metas)
        log.info(
            "Wrote chats.json: %d dialogs (%d private, %d groups/supergroups, %d channels)",
            len(metas),
            sum(1 for m in metas if m["type"] in ("private", "bot")),
            sum(1 for m in metas if m["type"] in ("group", "supergroup")),
            sum(1 for m in metas if m["type"] == "channel"),
        )
        return results

    # -- messages ------------------------------------------------------------

    async def collect_chat(self, entity, meta: dict, *, no_media: bool = False) -> dict:
        chat_id = meta["id"]
        title = meta.get("title") or str(chat_id)
        jsonl = self.messages_dir / f"chat_{chat_id}.jsonl"

        if self.state.is_chat_done(chat_id):
            log.info("[%s] already collected (%d msgs) — skipping.", title, self.state.chat_recorded_count(chat_id))
            return {"chat_id": chat_id, "skipped": True}

        # Clean any partial page from a prior interrupted run, then resume.
        last_id = self.state.chat_last_id(chat_id)
        truncate_jsonl_after(jsonl, last_id)

        total = await self._message_total(entity)
        progress = Progress(total)
        log.info(
            "[%s] id=%s type=%s members=%s — collecting%s (resume from id=%s)",
            title, chat_id, meta.get("type"), meta.get("members_count"),
            "" if not no_media else " (no media)", last_id,
        )

        while True:
            current_min = self.state.chat_last_id(chat_id)
            page: list = []
            try:
                kwargs: dict = {"reverse": True, "limit": self.settings.page_size}
                if current_min > 0:
                    kwargs["min_id"] = current_min
                async for message in self.client.iter_messages(entity, **kwargs):
                    page.append(message)
                    if len(page) >= self.settings.page_size:
                        await self.page_rate.wait()
                        await self._flush_page(chat_id, page, jsonl, progress, no_media)
                        page = []
            except FloodWaitError as exc:
                ok = await handle_floodwait(exc, context=f"messages [{title}]")
                if page:
                    await self._flush_page(chat_id, page, jsonl, progress, no_media)
                    page = []
                if not ok:
                    log.warning("[%s] stopping due to excessive FloodWait.", title)
                    return {"chat_id": chat_id, "flood_skipped": True}
                continue
            except KeyboardInterrupt:
                # Flush what we have so resume is clean, then re-raise.
                if page:
                    await self._flush_page(chat_id, page, jsonl, progress, no_media)
                raise
            if page:
                await self._flush_page(chat_id, page, jsonl, progress, no_media)
            break

        recorded = self.state.chat_recorded_count(chat_id)
        self.state.mark_chat_done(chat_id, recorded)
        self.state.save()
        media_summary = ""
        if self.downloader and not no_media:
            media_summary = (
                ", media: downloaded=%d skipped=%d failed=%d"
                % (self.downloader.downloaded, self.downloader.skipped, self.downloader.failed)
            )
        log.info(
            "[%s] done: %d messages saved%s",
            title, recorded, media_summary,
        )
        return {"chat_id": chat_id, "messages": recorded}

    async def _flush_page(
        self,
        chat_id: int,
        page: list,
        jsonl: Path,
        progress: Progress,
        no_media: bool,
    ) -> None:
        # Resolve sender entities we have not seen yet (best-effort).
        sender_ids = [m.sender_id for m in page if m.sender_id]
        try:
            await self.users.resolve(sender_ids)
        except Exception as exc:  # noqa: BLE001 — sender lookup must never kill a run
            log.debug("sender resolve failed for chat %s: %s", chat_id, exc)

        records: list[dict] = []
        media_items: list[tuple[object, dict]] = []
        for message in page:
            rec = serialize_message(message, chat_id)
            records.append(rec)
            if rec["media"] is not None:
                media_items.append((message, rec["media"]))

        # Download media for the page (bounded concurrency + dedup), then attach
        # local paths back into the records before persisting them.
        if media_items and self.downloader and not no_media:
            paths = await self.downloader.download_page(media_items)
            for rec in records:
                if rec["media"] is not None:
                    local = paths.get(rec["media"]["message_id"])
                    if local:
                        rec["media"]["local_path"] = local

        append_jsonl(jsonl, records)
        for rec in records:
            self.state.record_message(chat_id, rec["id"])
        progress.advance(len(records))
        self.state.save()

        log.info(
            "chat %s: %s | rate %s | ETA %s%s",
            chat_id,
            progress.progress_str(),
            progress.rate_str(),
            progress.eta_str(),
            f" | media dl={self.downloader.downloaded}" if (self.downloader and not no_media) else "",
        )

    async def _message_total(self, entity) -> int | None:
        try:
            result = await self.client.get_messages(entity, limit=0)
        except FloodWaitError as exc:
            await handle_floodwait(exc, context="message total")
            return None
        except Exception as exc:  # noqa: BLE001
            log.debug("could not get message total: %s", exc)
            return None
        return getattr(result, "total", None)

    # -- users ---------------------------------------------------------------

    async def harvest_users(self, entity, limit: int = 200) -> int:
        """Scan recent messages just to collect sender entities for users.json."""
        sender_ids: list[int] = []
        try:
            async for message in self.client.iter_messages(entity, limit=limit):
                if message.sender_id:
                    sender_ids.append(message.sender_id)
        except FloodWaitError as exc:
            ok = await handle_floodwait(exc, context="harvest users")
            if not ok:
                return 0
        except Exception as exc:  # noqa: BLE001
            log.debug("harvest_users failed for one chat: %s", exc)
            return 0
        await self.users.resolve(sender_ids)
        return len(sender_ids)

    def export_users(self) -> None:
        self.users.save(self.export_dir / "users.json")


# ---------------------------------------------------------------------------
# factories
# ---------------------------------------------------------------------------

def export_messages_dir(export_dir: Path) -> Path:
    path = export_dir / "messages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_media_dir(export_dir: Path) -> Path:
    path = export_dir / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def build_collector(
    client: TelegramClient,
    settings: Settings,
    *,
    with_media: bool = True,
    resolve_users: bool = True,
) -> Collector:
    state = ProgressState(settings.export_dir)
    user_index = UserIndex(client, resolve_unknowns=resolve_users)
    downloader = None
    if with_media:
        media_root = export_media_dir(settings.export_dir)
        downloader = MediaDownloader(
            client,
            media_root,
            state,
            RateLimiter(settings.rate_media_delay),
            settings.media_concurrency,
        )
    return Collector(client, settings, state, user_index, downloader)
