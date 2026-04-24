import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from src.config import settings
from src.bot.commands import start_command, help_command, status_command
from src.bot.handlers.chat import chat_handler
from src.bot.middleware import auth_middleware
from src.scheduler.reminder_runner import init_scheduler

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

    # Minimal commands
    app.add_handler(CommandHandler("start", wrap(start_command)))
    app.add_handler(CommandHandler("help", wrap(help_command)))
    app.add_handler(CommandHandler("status", wrap(status_command)))

    # Everything else goes through chat handler (natural conversation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wrap(chat_handler)))

    return app


async def post_init(app: Application) -> None:
    user_id = settings.allowed_user_ids_list[0]
    init_scheduler(app.bot, chat_id=user_id)
    logger.info(f"Bot started. Allowed users: {settings.allowed_user_ids_list}")


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
