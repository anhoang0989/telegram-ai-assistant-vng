"""
Single handler for ALL text messages (no commands).
Forward tin nhắn → LLM Router (agentic) → trả lời về Telegram.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.db.session import AsyncSessionFactory
from src.db.repositories import conversation as conv_repo
from src.ai.llm_router import chat

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MSG = 4000  # Telegram limit is 4096, leave headroom


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    await update.message.chat.send_action("typing")

    async with AsyncSessionFactory() as session:
        history_records = await conv_repo.get_recent(session, user_id)
        history = [{"role": r.role, "content": r.content} for r in history_records]

        # Save user message first
        await conv_repo.save(session, user_id, "user", user_message)

        try:
            response_text, model_used = await chat(session, history, user_message)
        except Exception as e:
            logger.error(f"chat() error: {e}", exc_info=True)
            response_text = f"⚠️ Lỗi khi xử lý: {e}"
            model_used = "error"

        logger.info(f"Served by: {model_used}")

        # Save assistant response
        await conv_repo.save(session, user_id, "assistant", response_text)

    # Split long messages for Telegram
    for i in range(0, len(response_text), MAX_TELEGRAM_MSG):
        chunk = response_text[i:i + MAX_TELEGRAM_MSG]
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            # Fallback nếu Markdown parse lỗi
            await update.message.reply_text(chunk)
