"""
Single handler for ALL text messages (no commands).
Forward tin nhắn → LLM Router (agentic) → trả lời về Telegram.
Keys lấy từ DB per-user (BYOK).
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.db.session import AsyncSessionFactory
from src.db.repositories import conversation as conv_repo
from src.db.repositories import user_keys as keys_repo
from src.ai.llm_router import chat

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MSG = 4000

NO_KEYS_MESSAGE = (
    "🔒 Bạn chưa setup API keys. Làm theo các bước:\n\n"
    "1️⃣ Lấy Gemini key miễn phí: https://aistudio.google.com/apikey\n"
    "2️⃣ Lấy Groq key miễn phí: https://console.groq.com/keys\n"
    "3️⃣ Nhắn bot:\n"
    "`/setkey gemini <KEY_CỦA_BẠN>`\n"
    "`/setkey groq <KEY_CỦA_BẠN>`\n\n"
    "Xong là chat được ngay. Key được mã hoá an toàn."
)


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    async with AsyncSessionFactory() as session:
        gemini_key, groq_key = await keys_repo.get_decrypted_keys(session, user_id)

        if not gemini_key or not groq_key:
            missing = []
            if not gemini_key:
                missing.append("Gemini")
            if not groq_key:
                missing.append("Groq")
            await update.message.reply_text(
                f"🔒 Thiếu key: {', '.join(missing)}.\n\n" + NO_KEYS_MESSAGE,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            return

        await update.message.chat.send_action("typing")

        history_records = await conv_repo.get_recent(session, user_id)
        history = [{"role": r.role, "content": r.content} for r in history_records]

        await conv_repo.save(session, user_id, "user", user_message)

        try:
            response_text, model_used = await chat(
                session, user_id, history, user_message, gemini_key, groq_key,
            )
        except Exception as e:
            logger.error(f"chat() error: {e}", exc_info=True)
            response_text = f"⚠️ Lỗi khi xử lý: {e}"
            model_used = "error"

        logger.info(f"[{user_id}] Served by: {model_used}")
        await conv_repo.save(session, user_id, "assistant", response_text)

    for i in range(0, len(response_text), MAX_TELEGRAM_MSG):
        chunk = response_text[i:i + MAX_TELEGRAM_MSG]
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(chunk)
