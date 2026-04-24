import logging
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update
from telegram.ext import BaseHandler
from src.config import settings

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter: max 30 messages/minute per user
_message_timestamps: dict[int, list[datetime]] = defaultdict(list)
RATE_LIMIT = 30
RATE_WINDOW = timedelta(minutes=1)


def is_allowed(user_id: int) -> bool:
    return user_id in settings.allowed_user_ids_list


def check_rate_limit(user_id: int) -> bool:
    now = datetime.utcnow()
    timestamps = _message_timestamps[user_id]
    # Remove old timestamps outside the window
    _message_timestamps[user_id] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_message_timestamps[user_id]) >= RATE_LIMIT:
        return False
    _message_timestamps[user_id].append(now)
    return True


async def auth_middleware(update: Update, context, next_handler):
    user = update.effective_user
    if user is None:
        return

    if not is_allowed(user.id):
        logger.warning(f"Blocked unauthorized user {user.id} (@{user.username})")
        await update.effective_message.reply_text("⛔ Bạn không có quyền sử dụng bot này.")
        return

    if not check_rate_limit(user.id):
        logger.warning(f"Rate limit hit for user {user.id}")
        await update.effective_message.reply_text("⚠️ Bạn gửi quá nhiều tin nhắn. Vui lòng chờ 1 phút.")
        return

    logger.info(f"[{user.id}] {update.effective_message.text or '(non-text)'}")
    return await next_handler(update, context)
