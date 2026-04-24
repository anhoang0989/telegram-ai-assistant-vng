"""
Text handler: 3 paths
  1. awaiting_email → user đang đăng ký, lưu email → notify admin
  2. awaiting_key → user đang nhập key, lưu encrypted → confirm
  3. default → chat với LLM (cần approved + có keys)
"""
import logging
import re
from telegram import Update
from telegram.ext import ContextTypes
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import conversation as conv_repo
from src.db.repositories import user_keys as keys_repo
from src.db.repositories import approvals as appr_repo
from src.ai.llm_router import chat
from src.bot.callbacks import approval_keyboard

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MSG = 4000

EMAIL_OR_DOMAIN_RE = re.compile(r"^[A-Za-z0-9._%+\-]+(?:@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}|\.[A-Za-z]{2,})$")


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    text = update.message.text or ""

    # Flow 1: signup — user đang nhập email/domain
    if context.user_data.get("awaiting_email"):
        await _handle_signup(update, context, text)
        return

    # Flow 2: key input — user đang nhập API key
    if context.user_data.get("awaiting_key"):
        await _handle_key_input(update, context, text)
        return

    # Flow 3: normal chat
    async with AsyncSessionFactory() as session:
        gemini_key, groq_key = await keys_repo.get_decrypted_keys(session, user_id)

        if not gemini_key or not groq_key:
            missing = []
            if not gemini_key:
                missing.append("Gemini")
            if not groq_key:
                missing.append("Groq")
            await update.message.reply_text(
                f"🔒 Đại hiệp còn thiếu key: {', '.join(missing)}.\n\nGõ /setkey để nhập."
            )
            return

        await update.message.chat.send_action("typing")

        history_records = await conv_repo.get_recent(session, user_id)
        history = [{"role": r.role, "content": r.content} for r in history_records]

        await conv_repo.save(session, user_id, "user", text)

        try:
            response_text, model_used = await chat(
                session, user_id, history, text, gemini_key, groq_key,
            )
        except Exception as e:
            logger.error(f"chat() error: {e}", exc_info=True)
            response_text = f"⚠️ Tại hạ gặp lỗi khi xử lý: {e}"
            model_used = "error"

        logger.info(f"[{user_id}] Served by: {model_used}")
        await conv_repo.save(session, user_id, "assistant", response_text)

    for i in range(0, len(response_text), MAX_TELEGRAM_MSG):
        chunk = response_text[i:i + MAX_TELEGRAM_MSG]
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(chunk)


async def _handle_signup(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    user = update.effective_user
    text = text.strip().lower()

    if not EMAIL_OR_DOMAIN_RE.match(text):
        await update.message.reply_text(
            "⚠️ Email/domain không hợp lệ. Thử lại (vd: `anh@vng.com.vn` hoặc `vnggames.com`):",
            parse_mode="Markdown",
        )
        return

    async with AsyncSessionFactory() as session:
        row = await appr_repo.create_pending(
            session,
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            email_or_domain=text,
        )

    context.user_data.pop("awaiting_email", None)

    await update.message.reply_text(
        "✅ Tại hạ đã nhận yêu cầu của đại hiệp.\n"
        f"📧 Email/domain: `{text}`\n\n"
        "⏳ Vui lòng chờ admin duyệt. Tại hạ sẽ báo lại khi có kết quả.",
        parse_mode="Markdown",
    )

    # Notify admin
    try:
        uname = f"@{user.username}" if user.username else "(no username)"
        admin_text = (
            "🆕 *Yêu cầu đăng ký mới*\n\n"
            f"👤 *{user.full_name or 'Không rõ tên'}* {uname}\n"
            f"🆔 `{user.id}`\n"
            f"📧 `{text}`"
        )
        await context.bot.send_message(
            chat_id=settings.admin_user_id,
            text=admin_text,
            parse_mode="Markdown",
            reply_markup=approval_keyboard(user.id),
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")


async def _handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    user_id = update.effective_user.id
    provider = context.user_data.pop("awaiting_key", None)
    key = text.strip()

    if len(key) < 10 or " " in key or "\n" in key:
        await update.message.reply_text(
            "⚠️ Key trông không hợp lệ. Gõ /setkey để thử lại."
        )
        return

    async with AsyncSessionFactory() as session:
        if provider == "gemini":
            await keys_repo.set_keys(session, user_id, gemini_key=key)
        elif provider == "groq":
            await keys_repo.set_keys(session, user_id, groq_key=key)

    # Delete the key message to hide it from chat
    try:
        await update.message.delete()
    except Exception:
        pass

    label = "Gemini" if provider == "gemini" else "Groq"
    await update.effective_chat.send_message(
        f"✅ Tại hạ đã lưu {label} key (đã mã hoá). Tin nhắn chứa key đã xoá.\n\n"
        "Gõ /mykey để kiểm tra, /setkey để nhập thêm key khác."
    )
