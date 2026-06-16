"""Resume state persisted to disk.

We write messages incrementally (JSONL) and track, per chat, the highest message
id already persisted. On resume we ask Telethon for messages with id > that
last id, so no duplicates and no wasted re-download.

Media downloads are deduplicated by a stable key (document_id / photo_id, or a
chat:message fallback) so a re-run never downloads the same file twice.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .logging_setup import get_logger

log = get_logger("state")

_CHAT_DONE = "done"
_CHAT_IN_PROGRESS = "in_progress"


class ProgressState:
    def __init__(self, export_dir: Path) -> None:
        self.export_dir = export_dir
        self.path = export_dir / "state.json"
        self._data: dict = self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> dict:
        if not self.path.exists():
            return {"chats": {}, "downloaded_media": {}}
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("state.json unreadable (%s); starting fresh.", exc)
            return {"chats": {}, "downloaded_media": {}}
        data.setdefault("chats", {})
        data.setdefault("downloaded_media", {})
        return data

    def save(self) -> None:
        """Atomic write: temp file + os.replace()."""
        self.export_dir.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".state-", suffix=".tmp", dir=str(self.export_dir)
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # -- chat progress -------------------------------------------------------

    def chat_status(self, chat_id: int) -> str | None:
        entry = self._data["chats"].get(str(chat_id))
        return entry.get("status") if entry else None

    def chat_last_id(self, chat_id: int) -> int:
        entry = self._data["chats"].get(str(chat_id))
        if not entry:
            return 0
        return int(entry.get("last_message_id", 0))

    def chat_recorded_count(self, chat_id: int) -> int:
        entry = self._data["chats"].get(str(chat_id))
        if not entry:
            return 0
        return int(entry.get("message_count", 0))

    def record_message(self, chat_id: int, message_id: int) -> None:
        """Update the high-water mark for a chat (assumes ascending message ids)."""
        key = str(chat_id)
        entry = self._data["chats"].setdefault(
            key,
            {"status": _CHAT_IN_PROGRESS, "last_message_id": 0, "message_count": 0},
        )
        entry["status"] = _CHAT_IN_PROGRESS
        if message_id > int(entry.get("last_message_id", 0)):
            entry["last_message_id"] = message_id
        entry["message_count"] = int(entry.get("message_count", 0)) + 1

    def mark_chat_done(self, chat_id: int, total: int | None = None) -> None:
        entry = self._data["chats"].setdefault(
            str(chat_id),
            {"status": _CHAT_DONE, "last_message_id": 0, "message_count": 0},
        )
        entry["status"] = _CHAT_DONE
        if total is not None:
            entry["message_count"] = total

    def is_chat_done(self, chat_id: int) -> bool:
        return self.chat_status(chat_id) == _CHAT_DONE

    # -- media dedup ---------------------------------------------------------

    def media_key(self, media_meta: dict) -> str:
        chat_id = media_meta.get("chat_id")
        msg_id = media_meta.get("message_id")
        doc_id = media_meta.get("document_id")
        photo_id = media_meta.get("photo_id")
        if doc_id:
            return f"doc:{doc_id}"
        if photo_id:
            return f"photo:{photo_id}"
        return f"msg:{chat_id}:{msg_id}"

    def is_media_downloaded(self, key: str) -> bool:
        return key in self._data["downloaded_media"]

    def mark_media_downloaded(self, key: str, local_path: str, size: int | None) -> None:
        self._data["downloaded_media"][key] = {
            "local_path": local_path,
            "size": size,
        }
