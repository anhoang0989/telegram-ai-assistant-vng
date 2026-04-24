"""
Inline button callbacks:
  - approve:<user_id> / reject:<user_id>  → admin duyệt user
  - setkey:gemini / setkey:groq            → user chọn loại key cần nhập
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import approvals as appr_repo

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data = query.data or ""

    if data.startswith("approve:") or data.startswith("reject:"):
        await _handle_approval(update, context, data)
    elif data.startswith("setkey:"):
        await _handle_setkey(update, context, data)
    else:
        logger.warning(f"Unknown callback data: {data}")


async def _handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    query = update.callback_query
    actor = update.effective_user

    if actor.id != settings.admin_user_id:
        await query.edit_message_text("⛔ Chỉ admin mới được duyệt.")
        return

    action, user_id_str = data.split(":", 1)
    target_user_id = int(user_id_str)
    new_status = "approved" if action == "approve" else "rejected"

    async with AsyncSessionFactory() as session:
        row = await appr_repo.set_status(session, target_user_id, new_status)

    if row is None:
        await query.edit_message_text("❌ Không tìm thấy yêu cầu này.")
        return

    # Update admin's message
    verb = "✅ Đã duyệt" if new_status == "approved" else "❌ Đã từ chối"
    original = query.message.text or ""
    await query.edit_message_text(f"{original}\n\n━━━━━\n{verb} bởi admin.")

    # Notify the user
    try:
        if new_status == "approved":
            kb = _setkey_keyboard()
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "🎉 Đại hiệp đã được tại hạ duyệt!\n\n"
                    "Bước tiếp theo — setup API keys cá nhân (miễn phí):\n"
                    "🔹 Gemini: https://aistudio.google.com/apikey\n"
                    "🔹 Groq: https://console.groq.com/keys\n\n"
                    "Chọn loại key muốn nhập:"
                ),
                reply_markup=kb,
                disable_web_page_preview=True,
            )
        else:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="⛔ Rất tiếc, yêu cầu của đại hiệp đã bị từ chối.",
            )
    except Exception as e:
        logger.error(f"Failed to notify user {target_user_id}: {e}")


async def _handle_setkey(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    query = update.callback_query
    _, provider = data.split(":", 1)
    if provider not in ("gemini", "groq"):
        return

    context.user_data["awaiting_key"] = provider
    label = "Gemini" if provider == "gemini" else "Groq"
    link = (
        "https://aistudio.google.com/apikey"
        if provider == "gemini"
        else "https://console.groq.com/keys"
    )

    await query.edit_message_text(
        f"🔑 Đại hiệp vui lòng paste {label} key vào tin nhắn tiếp theo.\n\n"
        f"Lấy key tại: {link}\n\n"
        f"Gõ /cancel để huỷ.",
        disable_web_page_preview=True,
    )


def _setkey_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 Nhập key Gemini", callback_data="setkey:gemini"),
            InlineKeyboardButton("🔑 Nhập key Groq", callback_data="setkey:groq"),
        ]
    ])


def approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"reject:{user_id}"),
        ]
    ])


def setkey_keyboard() -> InlineKeyboardMarkup:
    return _setkey_keyboard()
