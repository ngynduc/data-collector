"""Telethon client construction + connection management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from telethon import TelegramClient

from .config import Settings


def build_client(settings: Settings) -> TelegramClient:
    """Build a Telethon client from settings (proxy-aware). No connect here."""
    settings.validate()
    proxy = None
    if settings.proxy is not None:
        # Telethon accepts (scheme, host, port) or socks kwargs; the tuple form
        # works for both PySocks SOCKS proxies and HTTP proxies.
        p = settings.proxy
        proxy = (p.scheme, p.host, p.port, True, p.username, p.password)

    return TelegramClient(
        settings.session_name,
        settings.api_id,
        settings.api_hash,
        proxy=proxy,
        connection_retries=5,
        retry_delay=2,
        request_retries=5,
        flood_sleep_threshold=60,  # telethon auto-sleeps short floodwaits itself
    )


@asynccontextmanager
async def connected_client(settings: Settings) -> AsyncIterator[TelegramClient]:
    """Context manager that connects and disconnects a Telethon client."""
    client = build_client(settings)
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()
