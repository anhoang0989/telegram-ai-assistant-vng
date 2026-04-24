"""
Rate limit middleware. No user whitelist — bất kỳ ai có API key đều dùng được.
Key enforcement xảy ra trong chat handler (không phải ở đây, vì /start & /help
cần cho phép user mới vào để setup key).
"""
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update

logger = logging.getLogger(__name__)

_message_timestamps: dict[int, list[datetime]] = defaultdict(list)
RATE_LIMIT = 30
RATE_WINDOW = timedelta(minutes=1)


def check_rate_limit(user_id: int) -> bool:
    now = datetime.utcnow()
    timestamps = _message_timestamps[user_id]
    _message_timestamps[user_id] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_message_timestamps[user_id]) >= RATE_LIMIT:
        return False
    _message_timestamps[user_id].append(now)
    return True


async def auth_middleware(update: Update, context, next_handler):
    user = update.effective_user
    if user is None:
        return

    if not check_rate_limit(user.id):
        logger.warning(f"Rate limit hit for user {user.id}")
        await update.effective_message.reply_text("⚠️ Bạn gửi quá nhiều tin nhắn. Chờ 1 phút rồi thử lại.")
        return

    logger.info(f"[{user.id}] {update.effective_message.text or '(non-text)'}")
    return await next_handler(update, context)
