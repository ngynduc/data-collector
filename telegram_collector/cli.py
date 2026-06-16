"""Command-line interface.

Commands:
    telegram-collector login
    telegram-collector collect [--chat <id|username>] [--no-media] [--type T] [--limit N]
    telegram-collector export-users [--chat <id|username>] [--per-chat N]
    telegram-collector status
"""

from __future__ import annotations

import asyncio
import sys

import click

from .auth import ensure_authorized, interactive_login
from .client import connected_client
from .collector import build_collector
from .config import Settings, load_settings
from .logging_setup import configure_logging, get_logger
from .serializers import serialize_entity
from .state import ProgressState

log = get_logger("cli")


def _run(coro):
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        click.echo("\nInterrupted by user. Progress has been saved — re-run to resume.")
        sys.exit(130)


def _parse_chat(value: str):
    """Accept a chat id (int, optionally with -100 prefix) or a @username."""
    value = value.strip().lstrip("@")
    try:
        return int(value)
    except ValueError:
        return value  # treat as username


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.version_option(package_name="telegram-collector")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Export your own Telegram account data via the MTProto API (Telethon)."""
    configure_logging(verbose=verbose)
    ctx.ensure_object(dict)
    ctx.obj["settings"] = load_settings()


@main.command()
@click.pass_context
def login(ctx: click.Context) -> None:
    """Interactive login: phone -> OTP -> 2FA. Saves the session file."""
    settings: Settings = ctx.obj["settings"]

    async def run() -> None:
        async with connected_client(settings) as client:
            await interactive_login(client)

    _run(run())


@main.command()
@click.option("--chat", "chat_filter", type=str, help="Collect a single chat by id or @username.")
@click.option(
    "--no-media", is_flag=True, help="Skip media downloads (messages still record media metadata)."
)
@click.option(
    "--type",
    "type_filter",
    type=click.Choice(["private", "bot", "group", "supergroup", "channel"], case_sensitive=False),
    help="Only collect chats of this type (ignored with --chat).",
)
@click.option(
    "--limit",
    "chat_limit",
    type=int,
    default=0,
    help="Max number of chats to collect (0 = all).",
)
@click.pass_context
def collect(
    ctx: click.Context,
    chat_filter: str | None,
    no_media: bool,
    type_filter: str | None,
    chat_limit: int,
) -> None:
    """Crawl dialogs and write messages + media. Resumable on interrupt."""
    settings: Settings = ctx.obj["settings"]

    async def run() -> None:
        async with connected_client(settings) as client:
            await ensure_authorized(client)
            collector = await build_collector(client, settings, with_media=not no_media)

            await collector.export_account()

            if chat_filter:
                entity = await client.get_entity(_parse_chat(chat_filter))
                meta = serialize_entity(entity)
                await collector.collect_chat(entity, meta, no_media=no_media)
            else:
                pairs = await collector.collect_dialogs()
                selected = pairs
                if type_filter:
                    selected = [(m, e) for m, e in pairs if m["type"] == type_filter.lower()]
                if chat_limit and chat_limit > 0:
                    selected = selected[:chat_limit]
                log.info(
                    "Collecting %d chat(s) (of %d listed)%s.",
                    len(selected), len(pairs), " without media" if no_media else "",
                )
                for meta, entity in selected:
                    await collector.dialog_rate.wait()
                    await collector.collect_chat(entity, meta, no_media=no_media)

            collector.export_users()

    _run(run())


@main.command("export-users")
@click.option("--chat", "chat_filter", type=str, help="Harvest users from a single chat only.")
@click.option(
    "--per-chat",
    type=int,
    default=200,
    show_default=True,
    help="Recent messages to scan per chat for senders.",
)
@click.pass_context
def export_users(ctx: click.Context, chat_filter: str | None, per_chat: int) -> None:
    """Build users.json from senders seen in recent messages (no full crawl)."""
    settings: Settings = ctx.obj["settings"]

    async def run() -> None:
        async with connected_client(settings) as client:
            await ensure_authorized(client)
            collector = await build_collector(client, settings, with_media=False)
            await collector.export_account()

            if chat_filter:
                entity = await client.get_entity(_parse_chat(chat_filter))
                scanned = await collector.harvest_users(entity, limit=per_chat)
                log.info("Scanned %d recent messages for users in chat %s.", scanned, chat_filter)
            else:
                pairs = await collector.collect_dialogs()
                total_scanned = 0
                for meta, entity in pairs:
                    await collector.dialog_rate.wait()
                    total_scanned += await collector.harvest_users(entity, limit=per_chat)
                log.info("Scanned %d recent messages across %d chats.", total_scanned, len(pairs))

            collector.export_users()

    _run(run())


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show collection progress from state.json (no network)."""
    settings: Settings = ctx.obj["settings"]
    state = ProgressState(settings.export_dir)
    chats = state._data.get("chats", {})
    if not chats:
        click.echo(f"No state yet at {state.path}")
        return
    done = sum(1 for v in chats.values() if v.get("status") == "done")
    in_prog = sum(1 for v in chats.values() if v.get("status") == "in_progress")
    total_msgs = sum(int(v.get("message_count", 0)) for v in chats.values())
    media = state._data.get("downloaded_media", {})
    click.echo(f"State file: {state.path}")
    click.echo(f"Chats tracked: {len(chats)} ({done} done, {in_prog} in progress)")
    click.echo(f"Messages recorded: {total_msgs}")
    click.echo(f"Media downloaded: {len(media)}")


if __name__ == "__main__":
    main()
