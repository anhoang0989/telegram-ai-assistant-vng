import logging
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from src.config import settings
from src.bot.commands import (
    start_command,
    help_command,
    status_command,
    setkey_command,
    mykey_command,
    removekey_command,
    cancel_command,
    pending_command,
    schedules_command,
    notes_command,
    tasks_command,
    listmodels_command,
    members_command,
)
from src.bot.callbacks import handle_callback
from src.bot.handlers.chat import chat_handler
from src.bot.middleware import auth_middleware
from src.scheduler.reminder_runner import init_scheduler
from src.db.session import engine
from src.db.models import Base

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def wrap(handler_func):
    async def wrapped(update, context):
        return await auth_middleware(update, context, handler_func)
    return wrapped


def build_app() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", wrap(start_command)))
    app.add_handler(CommandHandler("help", wrap(help_command)))
    app.add_handler(CommandHandler("status", wrap(status_command)))
    app.add_handler(CommandHandler("setkey", wrap(setkey_command)))
    app.add_handler(CommandHandler("mykey", wrap(mykey_command)))
    app.add_handler(CommandHandler("removekey", wrap(removekey_command)))
    app.add_handler(CommandHandler("cancel", wrap(cancel_command)))
    app.add_handler(CommandHandler("pending", wrap(pending_command)))
    app.add_handler(CommandHandler("schedules", wrap(schedules_command)))
    app.add_handler(CommandHandler("notes", wrap(notes_command)))
    app.add_handler(CommandHandler("tasks", wrap(tasks_command)))
    app.add_handler(CommandHandler("listmodels", wrap(listmodels_command)))
    app.add_handler(CommandHandler("members", wrap(members_command)))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wrap(chat_handler)))
    return app


async def init_db() -> None:
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migration: thêm cột topic vào notes nếu chưa có (an toàn idempotent)
        await conn.execute(text(
            "ALTER TABLE notes ADD COLUMN IF NOT EXISTS topic VARCHAR(255)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_notes_topic ON notes(topic)"
        ))
    logger.info("DB tables ready.")


async def set_bot_menu(app: Application) -> None:
    commands = [
        BotCommand("start", "Bắt đầu / đăng ký"),
        BotCommand("schedules", "Xem lịch đã đặt"),
        BotCommand("notes", "Xem note đã lưu"),
        BotCommand("tasks", "Xem task / action items pending"),
        BotCommand("setkey", "Nhập API key (Gemini/Groq)"),
        BotCommand("mykey", "Xem trạng thái API keys"),
        BotCommand("removekey", "Xoá API keys"),
        BotCommand("status", "Xem quota còn lại"),
        BotCommand("help", "Hướng dẫn"),
        BotCommand("cancel", "Huỷ flow đang chờ input"),
    ]
    await app.bot.set_my_commands(commands)


async def post_init(app: Application) -> None:
    await init_db()
    await set_bot_menu(app)
    init_scheduler(app.bot)
    logger.info(
        f"Bot started (multi-tenant BYOK). Admin: {settings.admin_user_id}\n"
        f"Configured tiers: "
        f"{settings.llm_tier1} → {settings.llm_tier2} → {settings.llm_tier3} → "
        f"{settings.llm_tier4} → {settings.llm_tier5} → {settings.llm_tier6} → {settings.llm_tier7}\n"
        f"⚠️ Nếu thấy 404 NOT_FOUND, dùng /listmodels (admin) để xem tên model API thực tế."
    )


def main() -> None:
    app = build_app()
    app.post_init = post_init
    if settings.bot_mode == "webhook":
        app.run_webhook(
            listen="0.0.0.0",
            port=settings.webhook_port,
            webhook_url=f"{settings.webhook_url}/webhook",
        )
    else:
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
