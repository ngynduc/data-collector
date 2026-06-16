"""Structured-ish logging via rich. Human-readable but machine-greppable fields."""

from __future__ import annotations

import logging

from rich.logging import RichHandler

_LOG_FORMAT = "%(message)s"


def configure_logging(verbose: bool = False) -> logging.Logger:
    """Configure root logger with a rich handler. Idempotent."""
    root = logging.getLogger("telegram_collector")
    if getattr(root, "_tc_configured", False):
        return root

    level = logging.DEBUG if verbose else logging.INFO
    handler = RichHandler(
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=True,
        markup=False,
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="[%X]"))
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    root._tc_configured = True  # type: ignore[attr-defined]

    # Telethon is chatty on INFO; keep it quiet unless verbose.
    logging.getLogger("telethon").setLevel(logging.WARNING if not verbose else logging.INFO)
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"telegram_collector.{name}")
