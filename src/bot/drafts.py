"""
In-memory store cho drafts (note + schedule) chờ user confirm.
Mỗi user chỉ có 1 pending draft mỗi loại tại 1 thời điểm — đơn giản hoá UX.
TTL ngầm: nếu user không confirm, draft sẽ bị overwrite bởi draft mới.
"""
from __future__ import annotations
import time
import uuid

# user_id → draft dict
_PENDING_NOTES: dict[int, dict] = {}
_PENDING_SCHEDULES: dict[int, dict] = {}

# topic_hash → topic_name (để encode topic vào callback_data 64-byte limit)
_TOPIC_HASH: dict[str, str] = {}


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def put_note_draft(user_id: int, title: str, content: str, suggested_topic: str | None) -> str:
    draft_id = _short_id()
    _PENDING_NOTES[user_id] = {
        "draft_id": draft_id,
        "title": title,
        "content": content,
        "suggested_topic": suggested_topic,
        "chosen_topic": None,
        "ts": time.time(),
    }
    return draft_id


def get_note_draft(user_id: int) -> dict | None:
    return _PENDING_NOTES.get(user_id)


def update_note_topic(user_id: int, topic: str) -> dict | None:
    draft = _PENDING_NOTES.get(user_id)
    if draft is not None:
        draft["chosen_topic"] = topic
    return draft


def pop_note_draft(user_id: int) -> dict | None:
    return _PENDING_NOTES.pop(user_id, None)


def put_schedule_draft(user_id: int, title: str, scheduled_at: str, description: str | None, recurrence: str) -> str:
    draft_id = _short_id()
    _PENDING_SCHEDULES[user_id] = {
        "draft_id": draft_id,
        "title": title,
        "scheduled_at": scheduled_at,
        "description": description,
        "recurrence": recurrence,
        "ts": time.time(),
    }
    return draft_id


def get_schedule_draft(user_id: int) -> dict | None:
    return _PENDING_SCHEDULES.get(user_id)


def pop_schedule_draft(user_id: int) -> dict | None:
    return _PENDING_SCHEDULES.pop(user_id, None)


def hash_topic(topic: str) -> str:
    """Map topic name → short hash for callback_data (Telegram limit 64 bytes)."""
    h = uuid.uuid5(uuid.NAMESPACE_OID, topic).hex[:10]
    _TOPIC_HASH[h] = topic
    return h


def resolve_topic_hash(h: str) -> str | None:
    return _TOPIC_HASH.get(h)
