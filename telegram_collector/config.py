"""Configuration loaded from environment / .env file.

No secrets are ever hardcoded. Copy .env.example -> .env and fill it in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class ProxyConfig:
    """Parsed proxy URL (None if not set)."""

    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    session_name: str
    export_dir: Path

    rate_dialog_delay: float
    rate_page_delay: float
    rate_media_delay: float
    page_size: int
    media_concurrency: int
    proxy: ProxyConfig | None

    def __post_init__(self) -> None:
        # Resolve export_dir to an absolute path. Credential validation is
        # deferred to validate() so offline commands (e.g. `status`) work
        # without a configured .env.
        object.__setattr__(self, "export_dir", self.export_dir.resolve())

    def validate(self) -> None:
        """Raise if credentials are missing. Call before any network use."""
        if not self.api_id:
            raise RuntimeError("API_ID is not set. Fill in .env (see .env.example).")
        if not self.api_hash:
            raise RuntimeError("API_HASH is not set. Fill in .env (see .env.example).")


def _parse_proxy(raw: str) -> ProxyConfig | None:
    raw = raw.strip()
    if not raw:
        return None
    # urlsplit handles socks5://user:pass@host:port
    from urllib.parse import urlsplit

    parts = urlsplit(raw)
    if not parts.scheme or not parts.hostname or not parts.port:
        raise ValueError(f"Invalid PROXY url: {raw!r} (expected scheme://host:port)")
    return ProxyConfig(
        scheme=parts.scheme,
        host=parts.hostname,
        port=parts.port,
        username=parts.username,
        password=parts.password,
    )


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings from .env (or a custom env file) and environment variables."""
    if env_file is not None:
        load_dotenv(env_file)
    else:
        load_dotenv()  # picks up .env in cwd

    raw_api_id = os.getenv("API_ID", "").strip()
    try:
        api_id = int(raw_api_id) if raw_api_id else 0
    except ValueError as exc:
        raise RuntimeError(f"API_ID must be an integer, got {raw_api_id!r}") from exc

    return Settings(
        api_id=api_id,
        api_hash=os.getenv("API_HASH", "").strip(),
        session_name=os.getenv("SESSION_NAME", "collector_session").strip() or "collector_session",
        export_dir=Path(os.getenv("EXPORT_DIR", "telegram_export")),
        rate_dialog_delay=float(os.getenv("RATE_DIALOG_DELAY", "0.5")),
        rate_page_delay=float(os.getenv("RATE_PAGE_DELAY", "1.0")),
        rate_media_delay=float(os.getenv("RATE_MEDIA_DELAY", "0.5")),
        page_size=int(os.getenv("PAGE_SIZE", "100")),
        media_concurrency=max(1, int(os.getenv("MEDIA_CONCURRENCY", "3"))),
        proxy=_parse_proxy(os.getenv("PROXY", "")),
    )
