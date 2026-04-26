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
_PENDING_KNOWLEDGE: dict[int, dict] = {}
_PENDING_REPORTS: dict[int, dict] = {}

# topic_hash → topic_name (để encode topic vào callback_data 64-byte limit)
_TOPIC_HASH: dict[str, str] = {}

# product_hash → product_name (cho knowledge nav callback)
_PRODUCT_HASH: dict[str, str] = {}


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


def put_knowledge_draft(
    user_id: int,
    category: str,
    title: str,
    content: str,
    tags: list[str] | None,
    product: str | None = None,
    related: list[dict] | None = None,
) -> str:
    """related: list các entry liên quan cùng (product, category) để user
    review trước khi save (tránh duplicate / conflict).
    Format: [{'id': int, 'title': str}, ...]
    """
    draft_id = _short_id()
    _PENDING_KNOWLEDGE[user_id] = {
        "draft_id": draft_id,
        "product": product,  # final product (may be None = general)
        "category": category,
        "title": title,
        "content": content,
        "tags": tags,
        "related": related or [],
        "ts": time.time(),
    }
    return draft_id


def get_knowledge_draft(user_id: int) -> dict | None:
    return _PENDING_KNOWLEDGE.get(user_id)


def update_knowledge_product(user_id: int, product: str | None) -> dict | None:
    draft = _PENDING_KNOWLEDGE.get(user_id)
    if draft is not None:
        draft["product"] = product
    return draft


def pop_knowledge_draft(user_id: int) -> dict | None:
    return _PENDING_KNOWLEDGE.pop(user_id, None)


def put_report(user_id: int, filename: str, html: str, summary: str | None) -> None:
    """LLM tool export_html_report → store HTML + filename ở đây.
    Chat handler sẽ pop sau khi LLM agentic loop xong và gửi file qua send_document.
    """
    _PENDING_REPORTS[user_id] = {
        "filename": filename,
        "html": html,
        "summary": summary,
        "ts": time.time(),
    }


def get_report(user_id: int) -> dict | None:
    return _PENDING_REPORTS.get(user_id)


def pop_report(user_id: int) -> dict | None:
    return _PENDING_REPORTS.pop(user_id, None)


def hash_topic(topic: str) -> str:
    """Map topic name → short hash for callback_data (Telegram limit 64 bytes)."""
    h = uuid.uuid5(uuid.NAMESPACE_OID, topic).hex[:10]
    _TOPIC_HASH[h] = topic
    return h


def resolve_topic_hash(h: str) -> str | None:
    return _TOPIC_HASH.get(h)


def hash_product(product: str) -> str:
    """Map product name → short hash for callback_data."""
    h = uuid.uuid5(uuid.NAMESPACE_OID, "prod:" + product).hex[:10]
    _PRODUCT_HASH[h] = product
    return h


def resolve_product_hash(h: str) -> str | None:
    return _PRODUCT_HASH.get(h)
