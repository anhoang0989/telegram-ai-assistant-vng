import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from src.config import settings
from src.bot.commands import (
    start_command,
    help_command,
    status_command,
    setkey_command,
    mykey_command,
    removekey_command,
)
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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wrap(chat_handler)))
    return app


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB tables ready.")


async def post_init(app: Application) -> None:
    await init_db()
    init_scheduler(app.bot)
    logger.info("Bot started (multi-tenant BYOK mode).")


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
