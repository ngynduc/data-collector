# telegram-collector

Export **your own** Telegram account data through the official **MTProto API** via
[Telethon](https://github.com/LonamiWebs/Telethon). Collects account info, all
accessible dialogs, full message history, media attachments, and a user index.

> This tool is for exporting **your own** account. It uses a **user session**
> (not the Bot API) and talks directly to MTProto. It does **not** scrape
> Telegram Web. Use it only on accounts you own.

## Features

- **Authentication**: interactive phone → OTP → 2FA flow, with the session saved
  and reused on later runs (no repeated logins).
- **Account export**: id, username, phone, name, profile metadata.
- **Dialogs**: every private chat, group, supergroup, and channel you can access
  — with title, type, member count, permissions, timestamps, unread/pin state.
- **Messages**: full history per chat with pagination, persisted as JSONL so huge
  histories never load into memory. Captures id, sender, date, text, edit date,
  views, forwards, reply info, forwarded info, reactions, reply count, service
  actions.
- **Media**: photos, videos, documents, audio, voice, stickers — downloaded with
  bounded concurrency and de-duplicated across runs.
- **Reliability**: resume from the last saved message id, FloodWait handling,
  configurable rate limiting, crash-safe JSONL (partial tail pages are discarded
  on resume so no duplicate lines survive).
- **CLI**: `login`, `collect`, `export-users`, `status`.

## Requirements

- Python ≥ 3.11
- Telegram `api_id` and `api_hash` (see below)
- A Telegram **user** account

## Setup

```bash
# 1. clone / enter the project
cd data-collector

# 2. create a virtualenv and install (editably)
uv venv
uv pip install -e .
#   or with pip:
python -m venv .venv && source .venv/bin/activate && pip install -e .
```

This installs `telethon`, `cryptg` (faster encryption), `click`, `python-dotenv`,
and `rich`.

## Get your Telegram API credentials

1. Log in to <https://my.telegram.org>.
2. Open **API development tools**.
3. Create an application — you'll receive an `api_id` (number) and an
   `api_hash` (string).
4. Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

```dotenv
API_ID=123456
API_HASH=0123456789abcdef0123456789abcdef
SESSION_NAME=collector_session
EXPORT_DIR=telegram_export
# Rate limiting / reliability tuning (defaults shown)
RATE_DIALOG_DELAY=0.5
RATE_PAGE_DELAY=1.0
RATE_MEDIA_DELAY=0.5
PAGE_SIZE=100
MEDIA_CONCURRENCY=3
# PROXY=socks5://127.0.0.1:1080   # optional
```

> **Never commit `.env` or `*.session`.** They are already in `.gitignore`.
> A `.session` file is a stored authentication key — treat it like a password.

## Authentication

Run the login flow once in a real terminal (it needs interactive input):

```bash
telegram-collector login
```

You'll be prompted for:

1. your phone number (international format, e.g. `+15551234567`),
2. the login code Telegram sends you,
3. your 2FA password **only if** 2FA is enabled on the account.

On success a `collector_session.session` file is created. Subsequent commands load
this session and **do not** require a login.

## Collecting data

```bash
# collect everything: dialogs + full history + media + users
telegram-collector collect

# collect a single chat by id or @username
telegram-collector collect --chat -1001234567890
telegram-collector collect --chat @somechannel

# messages only, skip media downloads
telegram-collector collect --no-media

# only certain chat types
telegram-collector collect --type channel
telegram-collector collect --type private

# limit how many chats to process this run
telegram-collector collect --limit 10
```

Other commands:

```bash
# build users.json from senders in recent messages (no full crawl)
telegram-collector export-users
telegram-collector export-users --chat @somechannel --per-chat 500

# show progress from state.json (no network, no credentials needed)
telegram-collector status
```

You can also run it as a module:

```bash
python -m telegram_collector collect
# or
python main.py collect
```

### Resume / interruption

Collection is **resumable**. If you interrupt it (Ctrl+C) or it crashes, just
re-run the same command — it continues from the last persisted message id and
skips chats already fully collected. Media already downloaded is never
re-downloaded.

If Telegram rate-limits you, a `FloodWait` is logged and the tool sleeps it off
automatically (Telethon also auto-sleeps short waits under
`flood_sleep_threshold`).

## Output layout

```
telegram_export/
├── account.json              # your account info
├── chats.json                # all dialogs (array)
├── users.json                # all seen users (array)
├── state.json                # resume progress + media dedup index
├── messages/
│   └── chat_<id>.jsonl       # one JSON object per message per chat
└── media/
    ├── photos/
    ├── videos/
    ├── files/                # documents + stickers + gifs
    └── audio/                # audio + voice messages
```

**Messages** are JSONL (newline-delimited JSON) so each chat file streams
line-by-line — no full load into memory. Example line:

```json
{"id": 42, "chat_id": -1001234567890, "sender_id": 12345, "date": "2024-01-02T03:04:05+00:00",
 "edit_date": null, "text": "hello", "views": null, "forwards": null, "reply_count": null,
 "reply_to": null, "forwarded": null, "reactions": [], "media": null, "media_type": null,
 "action": null, "is_service": false}
```

A message **with media** includes a `media` object:

```json
"media": {
  "type": "document",
  "kind": "video",
  "file_name": "clip.mp4",
  "mime_type": "video/mp4",
  "size": 1234567,
  "document_id": 5550000000000,
  "message_id": 42,
  "chat_id": -1001234567890,
  "date": "2024-01-02T03:04:05+00:00",
  "local_path": "telegram_export/media/videos/clip.mp4"
}
```

`chats.json` entry:

```json
{"id": -1001234567890, "title": "My Channel", "type": "channel",
 "username": "somechannel", "members_count": 1234, "permissions": {...},
 "date": "2020-01-01T00:00:00+00:00", "last_message_date": "2024-05-01T10:00:00+00:00",
 "unread_count": 0, "pinned": false, "is_muted": false}
```

Chat `type` is one of: `private`, `bot`, `group`, `supergroup`, `channel`.

### Reading the JSONL

```bash
# pretty-print one message
head -n 1 telegram_export/messages/chat_-1001234567890.jsonl | python -m json.tool

# quick count
wc -l telegram_export/messages/chat_-1001234567890.jsonl
```

```python
import json
with open("telegram_export/messages/chat_-1001234567890.jsonl") as f:
    for line in f:
        msg = json.loads(line)
        print(msg["id"], msg.get("text", "")[:40])
```

## Tuning

Edit `.env` to adjust reliability vs. speed:

| Var | Meaning |
| --- | --- |
| `PAGE_SIZE` | Messages fetched per page (default 100). |
| `RATE_PAGE_DELAY` | Sleep between message pages (default 1.0s). |
| `RATE_DIALOG_DELAY` | Sleep between chats (default 0.5s). |
| `RATE_MEDIA_DELAY` | Sleep between media downloads (default 0.5s). |
| `MEDIA_CONCURRENCY` | Concurrent media downloads per page (default 3). |

If you hit frequent FloodWaits, raise the delays and/or lower `MEDIA_CONCURRENCY`.

## Security notes

- Credentials live in `.env`, never in code. `.env` and `*.session` are gitignored.
- The `.session` file grants access to your account — keep it private and delete
  it (`rm *.session`) when you no longer need it.
- `account.json` / `users.json` may contain phone numbers and names; treat the
  whole `telegram_export/` directory as sensitive.

## Project layout

```
telegram_collector/
├── __init__.py
├── __main__.py        # python -m entry
├── cli.py             # click commands
├── config.py          # .env -> Settings
├── client.py          # Telethon client factory (proxy-aware)
├── auth.py            # phone/OTP/2FA login + session reuse
├── serializers.py     # Telethon objects -> JSON dicts (account/dialogs/messages/media)
├── collector.py       # orchestration + resume loop
├── media.py           # media download (dedup + FloodWait-safe)
├── users.py           # global user index -> users.json
├── state.py           # resume progress + media dedup
├── storage.py         # atomic JSON, JSONL append, clean-resume truncate
├── ratelimit.py       # rate limiter + FloodWait helper
├── progress.py        # ETA / rate display
└── logging_setup.py   # rich structured logging
```

## Disclaimer

Export only data from your own account and only what Telegram permits you to
access. You are responsible for complying with Telegram's Terms of Service and
applicable law.
