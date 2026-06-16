"""Disk writers: atomic JSON, JSONL append, and clean-resume truncation."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .logging_setup import get_logger

log = get_logger("storage")


def write_json(path: Path, data: Any) -> None:
    """Atomic JSON write (temp file + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def append_jsonl(path: Path, records: Iterable[dict]) -> int:
    """Append records as JSON lines. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False))
            fh.write("\n")
            count += 1
    return count


def truncate_jsonl_after(path: Path, last_valid_id: int) -> int:
    """Remove any trailing JSONL lines whose 'id' > last_valid_id.

    Ensures a clean resume: a page half-written before a crash gets discarded
    and re-fetched, so no duplicate lines survive in the output.
    Returns number of lines removed.
    """
    if not path.exists():
        return 0

    # Find the byte offset to truncate at: keep everything up to and including
    # the last line whose id <= last_valid_id.
    keep_offset = 0
    removed = 0
    with path.open("rb") as fh:
        pos = 0
        for raw in fh:
            pos = fh.tell()
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                # Corrupt/partial tail line -> drop it and everything after.
                removed += 1
                break
            lid = obj.get("id")
            if isinstance(lid, int) and lid <= last_valid_id:
                keep_offset = pos  # end of this valid line
                continue
            # First line past the high-water mark: truncate here.
            removed += 1
            break

    if removed > 0:
        with path.open("r+b") as fh:
            fh.truncate(keep_offset)
        log.info("Truncated %s tail after id=%s (removed >=%d line).", path.name, last_valid_id, removed)
    return removed
