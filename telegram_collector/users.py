"""Global user index — collects every seen user into users.json."""

from __future__ import annotations

import asyncio

from telethon import TelegramClient

from .logging_setup import get_logger
from .serializers import serialize_user
from .storage import write_json

log = get_logger("users")


class UserIndex:
    def __init__(self, client: TelegramClient, resolve_unknowns: bool = True) -> None:
        self.client = client
        self.resolve_unknowns = resolve_unknowns
        self.users: dict[int, dict] = {}

    def add(self, entity) -> None:
        serialized = serialize_user(entity) if entity is not None else None
        if serialized and serialized["id"] not in self.users:
            self.users[serialized["id"]] = serialized

    def add_many(self, entities) -> None:
        for ent in entities:
            self.add(ent)

    async def resolve(self, user_ids: list[int]) -> None:
        """Batch-resolve user entities we have not seen yet."""
        if not self.resolve_unknowns:
            return
        unknown = [uid for uid in user_ids if uid and uid not in self.users]
        # Deduplicate while preserving order.
        seen: set[int] = set()
        unknown = [u for u in unknown if not (u in seen or seen.add(u))]
        if not unknown:
            return

        # Resolve in chunks; telethon accepts a list of ids to get_entity.
        for i in range(0, len(unknown), 100):
            chunk = unknown[i : i + 100]
            try:
                entities = await self.client.get_entity(chunk)
            except Exception as exc:  # noqa: BLE001
                log.debug("get_entity(%s) failed: %s; falling back per-id", chunk, exc)
                await self._resolve_one_by_one(chunk)
                continue
            if isinstance(entities, (list, tuple)):
                for ent in entities:
                    self.add(ent)
            else:
                self.add(entities)
            await asyncio.sleep(0)

    async def _resolve_one_by_one(self, ids: list[int]) -> None:
        for uid in ids:
            try:
                ent = await self.client.get_entity(uid)
                self.add(ent)
            except Exception as exc:  # noqa: BLE001
                log.debug("could not resolve user %s: %s", uid, exc)

    def as_list(self) -> list[dict]:
        return sorted(self.users.values(), key=lambda u: u["id"])

    def save(self, path) -> None:
        write_json(path, self.as_list())
        log.info("Wrote %d users to %s", len(self.users), path)
