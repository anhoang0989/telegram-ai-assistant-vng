import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import schedules as repo
from src.services.schedule_service import format_reminder

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_bot = None  # set at startup
_chat_id: int | None = None  # the allowed user's chat_id


def init_scheduler(bot, chat_id: int) -> AsyncIOScheduler:
    global _scheduler, _bot, _chat_id
    _bot = bot
    _chat_id = chat_id

    # Use sync PostgreSQL URL for APScheduler jobstore (strip +asyncpg)
    sync_url = settings.database_url.replace("+asyncpg", "")
    jobstores = {"default": SQLAlchemyJobStore(url=sync_url)}

    _scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone=settings.scheduler_timezone,
    )
    _scheduler.add_job(
        check_and_fire_reminders,
        "interval",
        minutes=1,
        id="reminder_checker",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started.")
    return _scheduler


async def check_and_fire_reminders() -> None:
    if _bot is None or _chat_id is None:
        return
    async with AsyncSessionFactory() as session:
        pending = await repo.get_pending_unnotified(session)
        for schedule in pending:
            try:
                text = await format_reminder(schedule)
                await _bot.send_message(chat_id=_chat_id, text=text, parse_mode="Markdown")
                await repo.mark_notified(session, schedule.id)
                logger.info(f"Reminder sent: {schedule.title}")
            except Exception as e:
                logger.error(f"Failed to send reminder {schedule.id}: {e}")
