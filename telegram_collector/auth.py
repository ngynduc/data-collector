"""Authentication: phone -> OTP -> optional 2FA password.

On first run, walks the interactive login flow and persists the session file
(<session_name>.session). On later runs the session is loaded and no login
is needed.
"""

from __future__ import annotations

import getpass
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from .logging_setup import get_logger

log = get_logger("auth")


def _prompt(prompt: str, *, password: bool = False) -> str:
    """Read input from terminal, hidden when password is requested."""
    if not sys.stdin.isatty():
        raise RuntimeError(
            f"Need interactive input for {prompt!r}, but no TTY is attached. "
            "Run `telegram-collector login` in a real terminal."
        )
    if password:
        return getpass.getpass(prompt)
    return input(prompt).strip()


async def interactive_login(client: TelegramClient) -> None:
    """Run the full interactive login flow if the session is not authorized."""
    if await client.is_user_authorized():
        me = await client.get_me()
        log.info("Session authorized as %s (id=%s). No login needed.", _display(me), me.id)
        return

    phone = _prompt("Enter your phone number (international format, e.g. +15551234567): ")
    await client.send_code_request(phone)

    code = _prompt("Enter the login code you received: ")
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        log.warning("2FA is enabled on this account.")
        while True:
            pwd = _prompt("Enter your 2FA password: ", password=True)
            try:
                await client.sign_in(password=pwd)
                break
            except Exception as exc:  # noqa: BLE001 — surface any auth failure clearly
                log.error("2FA sign-in failed: %s", exc)
                log.info("Try again (Ctrl+C to abort).")

    me = await client.get_me()
    log.info("Login successful. Signed in as %s (id=%s).", _display(me), me.id)
    log.info("Session saved to %s.session — future runs reuse it.", client.session.filename)


async def ensure_authorized(client: TelegramClient) -> None:
    """Fail fast if the stored session is invalid/expired (non-interactive)."""
    if await client.is_user_authorized():
        return
    raise RuntimeError(
        "Session is not authorized. Run `telegram-collector login` first to "
        "create a session."
    )


def _display(me) -> str:  # telethon User object
    parts = [me.first_name, me.last_name]
    name = " ".join(p for p in parts if p) or me.username or me.phone or "user"
    if me.username:
        return f"{name} (@{me.username})"
    return name
