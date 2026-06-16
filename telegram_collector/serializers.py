"""Pure data extraction: Telethon TL objects -> plain dicts ready for JSON.

Keeping serialization separate from network/crawl logic makes the output shape
easy to reason about and test.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from telethon.tl.types import (
    Channel,
    Chat,
    ChatBannedRights,
    Document,
    MessageActionChatAddUser,
    MessageActionChatCreate,
    MessageActionChatDeleteUser,
    MessageActionChatEditPhoto,
    MessageActionChatEditTitle,
    MessageActionChatJoinedByLink,
    MessageActionChatMigrateTo,
    MessageActionChannelCreate,
    MessageActionChannelMigrateFrom,
    MessageActionContactSignUp,
    MessageActionCustomAction,
    MessageActionEmpty,
    MessageActionGameScore,
    MessageActionHistoryClear,
    MessageActionPhoneCall,
    MessageActionPinMessage,
    MessageActionScreenshotTaken,
    MessageMediaContact,
    MessageMediaDocument,
    MessageMediaGeo,
    MessageMediaPhoto,
    MessageMediaPoll,
    MessageMediaWebPage,
    MessageReplyHeader,
    MessageReactions,
    MessageReplies,
    PeerChannel,
    PeerUser,
    Photo,
    ReactionCount,
    ReactionEmoji,
    User,
)

MediaSubdir = str

PHOTOS = "photos"
VIDEOS = "videos"
FILES = "files"
AUDIO = "audio"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _peer_info(peer) -> dict[str, Any] | None:
    if peer is None:
        return None
    if isinstance(peer, PeerUser):
        return {"type": "user", "id": peer.user_id}
    if isinstance(peer, PeerChannel):
        return {"type": "channel", "id": peer.channel_id}
    # PeerChat and anything else
    chat_id = getattr(peer, "chat_id", None)
    return {"type": "chat", "id": chat_id}


# ---------------------------------------------------------------------------
# account + users
# ---------------------------------------------------------------------------

def serialize_account(me: User) -> dict[str, Any]:
    return {
        "id": me.id,
        "username": me.username,
        "phone": me.phone,
        "first_name": me.first_name,
        "last_name": me.last_name,
        "name": _full_name(me),
        "is_bot": bool(me.bot),
        "verified": bool(getattr(me, "verified", False)),
        "restricted": bool(getattr(me, "restricted", False)),
        "scam": bool(getattr(me, "scam", False)),
        "fake": bool(getattr(me, "fake", False)),
        "status": _user_status(me.status),
        "lang_code": getattr(me, "lang_code", None),
        "photo": _photo_meta(me.photo),
    }


def serialize_user(user) -> dict[str, Any] | None:
    """Serialize a User for the global users.json index. None for non-users."""
    if user is None:
        return None
    if not isinstance(user, User):
        return None
    return {
        "id": user.id,
        "username": getattr(user, "username", None),
        "first_name": getattr(user, "first_name", None),
        "last_name": getattr(user, "last_name", None),
        "name": _full_name(user),
        "phone": getattr(user, "phone", None),
        "is_bot": bool(getattr(user, "bot", False)),
        "deleted": bool(getattr(user, "deleted", False)),
        "verified": bool(getattr(user, "verified", False)),
        "status": _user_status(user.status),
    }


def _full_name(user: User) -> str | None:
    parts = [user.first_name, user.last_name]
    name = " ".join(p for p in parts if p)
    return name or None


def _user_status(status) -> str:
    if status is None:
        return "unknown"
    return type(status).__name__.replace("UserStatus", "").lower() or "unknown"


def _photo_meta(photo) -> dict[str, Any] | None:
    if photo is None:
        return None
    if isinstance(photo, Photo):
        sizes = [getattr(s, "type", None) for s in photo.sizes]
        return {
            "id": photo.id,
            "date": _dt(photo.date),
            "sizes": sizes,
            "dc_id": getattr(photo, "dc_id", None),
        }
    # Stripped / legacy photo placeholders
    return {"raw": type(photo).__name__}


# ---------------------------------------------------------------------------
# dialogs
# ---------------------------------------------------------------------------

def entity_type(entity) -> str:
    if isinstance(entity, Channel):
        if getattr(entity, "megagroup", False):
            return "supergroup"
        if getattr(entity, "broadcast", False):
            return "channel"
        return "channel"
    if isinstance(entity, Chat):
        return "group"
    if isinstance(entity, User):
        return "bot" if getattr(entity, "bot", False) else "private"
    return "unknown"


def _entity_title(entity) -> str:
    if isinstance(entity, User):
        return _full_name(entity) or entity.username or str(entity.id)
    return getattr(entity, "title", None) or getattr(entity, "name", None) or str(entity.id)


def serialize_entity(entity) -> dict[str, Any]:
    """Dialog-like summary built from a raw entity (for the --chat path)."""
    members = None
    if isinstance(entity, (Channel, Chat)):
        members = getattr(entity, "participants_count", None)
    rights = getattr(entity, "default_banned_rights", None)
    return {
        "id": _entity_id(entity),
        "access_hash": str(getattr(entity, "access_hash", "") or "") or None,
        "title": _entity_title(entity),
        "type": entity_type(entity),
        "username": getattr(entity, "username", None),
        "members_count": members,
        "permissions": _banned_rights(rights),
        "date": _dt(getattr(entity, "date", None)),
        "last_message_date": None,
        "unread_count": 0,
        "unread_mentions_count": 0,
        "unread_mark": False,
        "pinned": False,
        "is_archived": False,
        "is_muted": False,
    }


def serialize_dialog(dialog) -> dict[str, Any]:
    entity = dialog.entity
    etype = entity_type(entity)

    members = None
    if isinstance(entity, (Channel, Chat)):
        members = getattr(entity, "participants_count", None)

    rights = getattr(entity, "default_banned_rights", None)

    return {
        "id": _entity_id(entity),
        "access_hash": str(getattr(entity, "access_hash", "") or "") or None,
        "title": dialog.title or dialog.name or "",
        "type": etype,
        "username": getattr(entity, "username", None),
        "members_count": members,
        "permissions": _banned_rights(rights),
        "date": _dt(getattr(entity, "date", None)),
        "last_message_date": _dt(dialog.date),
        "unread_count": getattr(dialog, "unread_count", 0),
        "unread_mentions_count": getattr(dialog, "unread_mentions_count", 0),
        "unread_mark": bool(getattr(dialog, "unread_mark", False)),
        "pinned": bool(getattr(dialog, "pinned", False)),
        "is_archived": bool(getattr(dialog, "archived", False)),
        "is_muted": _is_muted(dialog),
    }


def _entity_id(entity) -> int:
    raw = entity.id
    # Channels have a -100 prefix convention in bots; we store the raw id and
    # also a chat_id with the bot prefix for cross-tool compatibility.
    if isinstance(entity, Channel) and raw > 0:
        return int(f"-100{raw}")
    return raw


def _banned_rights(rights: ChatBannedRights | None) -> dict[str, Any] | None:
    if rights is None:
        return None
    flags = [
        "send_messages", "send_media", "send_stickers", "send_gifs", "send_games",
        "send_inline", "embed_links", "send_polls", "change_info", "invite_users",
        "pin_messages", "manage_topics", "send_media_albums",
    ]
    banned = {f: bool(getattr(rights, f, False)) for f in flags if getattr(rights, f, False)}
    return {
        "banned_actions": banned,
        "until_date": _dt(getattr(rights, "until_date", None)),
    }


def _is_muted(dialog) -> bool:
    notify = getattr(dialog, "notify_settings", None)
    if notify is None:
        return False
    return bool(getattr(notify, "mute_until", None))


# ---------------------------------------------------------------------------
# media classification + metadata
# ---------------------------------------------------------------------------

def classify_media(message) -> str | None:
    """Return one of: photo, video, voice, audio, sticker, file, or None."""
    media = message.media
    if media is None:
        return None
    if isinstance(media, MessageMediaPhoto) or message.photo:
        return "photo"
    doc = getattr(message, "document", None) or (
        media.document if isinstance(media, MessageMediaDocument) else None
    )
    if doc is None:
        # Non-document media (geo, contact, poll, webpage) — not downloadable
        return None
    return _document_kind(message, doc)


def _document_kind(message, doc: Document) -> str:
    # Voice / audio via attributes
    for attr in doc.attributes:
        kind = type(attr).__name__
        if kind == "DocumentAttributeAudio":
            return "voice" if getattr(attr, "voice", False) else "audio"
        if kind == "DocumentAttributeVideo":
            # round video (video note) has no_message set -> still video bucket
            return "video"
        if kind == "DocumentAttributeSticker":
            return "sticker"
    if message.sticker:
        return "sticker"
    if message.video or message.video_note:
        return "video"
    if message.gif:
        return "file"  # gif -> generic file bucket
    return "file"


def media_subdir(kind: str) -> MediaSubdir:
    return {
        "photo": PHOTOS,
        "video": VIDEOS,
        "voice": AUDIO,
        "audio": AUDIO,
        "sticker": FILES,
        "file": FILES,
    }.get(kind, FILES)


def serialize_media(message, chat_id: int, kind: str | None) -> dict[str, Any] | None:
    if kind is None:
        return None
    media = message.media
    doc: Document | None = getattr(message, "document", None)
    if isinstance(media, MessageMediaDocument) and doc is None:
        doc = media.document

    if kind == "photo":
        photo = message.photo or (media.photo if isinstance(media, MessageMediaPhoto) else None)
        photo_id = getattr(photo, "id", None) if photo else None
        # Photos don't have a filename; synthesize a stable one.
        file_name = f"photo_{chat_id}_{message.id}_{photo_id}.jpg" if photo_id else None
        mime = "image/jpeg"
        size = _photo_size(photo) if photo else None
        return {
            "type": "photo",
            "kind": kind,
            "file_name": file_name,
            "mime_type": mime,
            "size": size,
            "photo_id": photo_id,
            "document_id": None,
            "message_id": message.id,
            "chat_id": chat_id,
            "date": _dt(message.date),
        }

    if doc is None:
        return None

    file_name = _doc_filename(doc) or f"file_{chat_id}_{message.id}_{doc.id}"
    return {
        "type": "document",
        "kind": kind,
        "file_name": file_name,
        "mime_type": doc.mime_type,
        "size": doc.size,
        "document_id": doc.id,
        "message_id": message.id,
        "chat_id": chat_id,
        "date": _dt(message.date),
    }


def _doc_filename(doc: Document) -> str | None:
    from telethon.tl.types import DocumentAttributeFilename

    for attr in doc.attributes:
        if isinstance(attr, DocumentAttributeFilename) and getattr(attr, "file_name", None):
            return attr.file_name
    return None


def _photo_size(photo: Photo | None) -> int | None:
    if photo is None or not photo.sizes:
        return None
    last = photo.sizes[-1]
    return getattr(last, "size", None)


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------

_SERVICE_ACTIONS = {
    MessageActionChatCreate: "chat_create",
    MessageActionChatEditTitle: "edit_title",
    MessageActionChatEditPhoto: "edit_photo",
    MessageActionChatAddUser: "add_users",
    MessageActionChatDeleteUser: "delete_user",
    MessageActionChatJoinedByLink: "joined_by_link",
    MessageActionChatMigrateTo: "migrate_to",
    MessageActionChannelCreate: "channel_create",
    MessageActionChannelMigrateFrom: "migrate_from",
    MessageActionPinMessage: "pin_message",
    MessageActionPhoneCall: "phone_call",
    MessageActionGameScore: "game_score",
    MessageActionScreenshotTaken: "screenshot",
    MessageActionCustomAction: "custom",
    MessageActionHistoryClear: "history_clear",
    MessageActionContactSignUp: "contact_signup",
    MessageActionEmpty: "empty",
}


def serialize_message(message, chat_id: int) -> dict[str, Any]:
    """Serialize a Telethon Message into a JSON-safe dict.

    Sender/media lookups are resolved by the caller (we keep references by id);
    the caller also collects sender entities into the user index.
    """
    kind = classify_media(message)
    media_meta = serialize_media(message, chat_id, kind)

    return {
        "id": message.id,
        "chat_id": chat_id,
        "sender_id": message.sender_id,
        "date": _dt(message.date),
        "edit_date": _dt(message.edit_date),
        "text": message.text or "",
        "views": getattr(message, "views", None),
        "forwards": getattr(message, "forwards", None),
        "reply_count": _reply_count(message.replies),
        "reply_to": _reply_to(message.reply_to),
        "forwarded": _forwarded(message.fwd_from),
        "reactions": _reactions(message.reactions),
        "media": media_meta,
        "media_type": media_meta["kind"] if media_meta else None,
        "action": _action(message.action),
        "is_service": message.action is not None,
    }


def _reply_count(replies: MessageReplies | None) -> int | None:
    if replies is None:
        return None
    return getattr(replies, "replies", None)


def _reply_to(header: MessageReplyHeader | None) -> dict[str, Any] | None:
    if header is None:
        return None
    return {
        "id": getattr(header, "reply_to_msg_id", None),
        "top_id": getattr(header, "reply_to_top_id", None),
    }


def _forwarded(fwd) -> dict[str, Any] | None:
    if fwd is None:
        return None
    return {
        "date": _dt(fwd.date),
        "from": _peer_info(fwd.from_id),
        "from_name": getattr(fwd, "from_name", None),
        "channel_post": getattr(fwd, "channel_post", None),
        "saved_from_peer": _peer_info(getattr(fwd, "saved_from_peer", None)),
        "saved_from_msg_id": getattr(fwd, "saved_from_msg_id", None),
    }


def _reactions(reactions: MessageReactions | None) -> list[dict[str, Any]]:
    if reactions is None or not getattr(reactions, "results", None):
        return []
    out: list[dict[str, Any]] = []
    for rc in reactions.results:
        if not isinstance(rc, ReactionCount):
            continue
        emoji = None
        if isinstance(rc.reaction, ReactionEmoji):
            emoji = rc.reaction.emoticon
        out.append(
            {
                "emoticon": emoji,
                "reaction_type": type(rc.reaction).__name__,
                "count": rc.count,
                "chosen": bool(getattr(rc, "chosen", False)),
            }
        )
    return out


def _action(action) -> dict[str, Any] | None:
    if action is None:
        return None
    label = _SERVICE_ACTIONS.get(type(action), type(action).__name__)
    extra: dict[str, Any] = {}
    if isinstance(action, MessageActionChatAddUser):
        extra["users"] = list(action.users)
    elif isinstance(action, MessageActionChatDeleteUser):
        extra["user_id"] = action.user_id
    elif isinstance(action, MessageActionChatEditTitle):
        extra["title"] = action.title
    elif isinstance(action, MessageActionPhoneCall):
        extra["video"] = getattr(action, "video", False)
        extra["call_id"] = getattr(action, "id", None)
    elif isinstance(action, MessageActionCustomAction):
        extra["message"] = action.message
    return {"type": label, **extra}


def media_kind_for_media_object(media) -> str | None:
    """Classify a raw MessageMedia* object (used when media is detached)."""
    if isinstance(media, (MessageMediaPhoto,)):
        return "photo"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if isinstance(doc, Document):
            for attr in doc.attributes:
                kind = type(attr).__name__
                if kind == "DocumentAttributeAudio":
                    return "voice" if getattr(attr, "voice", False) else "audio"
                if kind == "DocumentAttributeVideo":
                    return "video"
                if kind == "DocumentAttributeSticker":
                    return "sticker"
            return "file"
    if isinstance(media, (MessageMediaGeo, MessageMediaContact, MessageMediaPoll, MessageMediaWebPage)):
        return None
    return None
