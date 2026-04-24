"""
Middleware: rate limit + approval gate.
- /start là lối duy nhất để user chưa approved tương tác (đăng ký + nhập email).
- Admin luôn được bypass approval check.
"""
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import approvals as appr_repo

logger = logging.getLogger(__name__)

_message_timestamps: dict[int, list[datetime]] = defaultdict(list)
RATE_LIMIT = 30
RATE_WINDOW = timedelta(minutes=1)

# Commands allowed regardless of approval status
PUBLIC_COMMANDS = {"/start", "/help"}


def check_rate_limit(user_id: int) -> bool:
    now = datetime.utcnow()
    timestamps = _message_timestamps[user_id]
    _message_timestamps[user_id] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_message_timestamps[user_id]) >= RATE_LIMIT:
        return False
    _message_timestamps[user_id].append(now)
    return True


def _is_public(update: Update) -> bool:
    msg = update.effective_message
    if msg is None or not msg.text:
        return False
    first_word = msg.text.split()[0].split("@")[0]
    return first_word in PUBLIC_COMMANDS


async def auth_middleware(update: Update, context, next_handler):
    user = update.effective_user
    if user is None:
        return

    if not check_rate_limit(user.id):
        logger.warning(f"Rate limit hit for user {user.id}")
        await update.effective_message.reply_text("⚠️ Đại hiệp gửi quá nhiều tin nhắn. Tạm nghỉ 1 phút rồi thử lại.")
        return

    # Admin bypass approval
    if user.id == settings.admin_user_id:
        logger.info(f"[admin:{user.id}] {update.effective_message.text or '(non-text)'}")
        return await next_handler(update, context)

    # Public commands (/start, /help) always allowed
    if _is_public(update):
        logger.info(f"[{user.id}] (public) {update.effective_message.text}")
        return await next_handler(update, context)

    # Check if pending signup flow (user_data flag set by /start)
    if context.user_data.get("awaiting_email"):
        logger.info(f"[{user.id}] (signup) {update.effective_message.text}")
        return await next_handler(update, context)

    # Otherwise require approval
    async with AsyncSessionFactory() as session:
        approved = await appr_repo.is_approved(session, user.id)
        row = await appr_repo.get(session, user.id)

    if not approved:
        if row is None:
            await update.effective_message.reply_text(
                "🔒 Đại hiệp chưa đăng ký. Gõ /start để bắt đầu."
            )
        elif row.status == "pending":
            await update.effective_message.reply_text(
                "⏳ Yêu cầu của đại hiệp đang chờ tại hạ duyệt. Vui lòng kiên nhẫn."
            )
        else:
            await update.effective_message.reply_text(
                "⛔ Yêu cầu của đại hiệp đã bị từ chối. Liên hệ tại hạ để biết thêm."
            )
        return

    logger.info(f"[{user.id}] {update.effective_message.text or '(non-text)'}")
    return await next_handler(update, context)
