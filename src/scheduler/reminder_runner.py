import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import schedules as repo
from src.db.repositories import knowledge as knowledge_repo
from src.db.repositories import user_keys as keys_repo
from src.db.models import UserApproval, Schedule
from src.services.schedule_service import format_reminder, TZ
from src.services.knowledge_digest import generate_digest
from src.bot.keyboards import snooze_keyboard

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_bot = None


def init_scheduler(bot) -> AsyncIOScheduler:
    global _scheduler, _bot
    _bot = bot

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
    # Daily digest 8:00 sáng giờ Việt Nam
    _scheduler.add_job(
        daily_digest,
        CronTrigger(hour=8, minute=0, timezone=settings.scheduler_timezone),
        id="daily_digest",
        replace_existing=True,
    )
    # Weekly knowledge digest — Chủ nhật 9:00 sáng giờ VN (day_of_week=0=Mon, 6=Sun)
    _scheduler.add_job(
        weekly_knowledge_digest,
        CronTrigger(day_of_week="sun", hour=9, minute=0, timezone=settings.scheduler_timezone),
        id="weekly_knowledge_digest",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started (reminders + daily digest 8:00 + weekly knowledge digest sun 9:00).")
    return _scheduler


async def check_and_fire_reminders() -> None:
    if _bot is None:
        return
    async with AsyncSessionFactory() as session:
        pending = await repo.get_pending_unnotified(session)
        for schedule in pending:
            try:
                text = await format_reminder(schedule)
                kb = snooze_keyboard(schedule.id)
                try:
                    await _bot.send_message(
                        chat_id=schedule.user_id,
                        text=text,
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                except Exception:
                    # Markdown fallback
                    await _bot.send_message(
                        chat_id=schedule.user_id,
                        text=text,
                        reply_markup=kb,
                    )
                await repo.mark_notified(session, schedule.id)
                logger.info(f"Reminder sent to {schedule.user_id}: {schedule.title}")
            except Exception as e:
                logger.error(f"Failed to send reminder {schedule.id}: {e}")


async def daily_digest() -> None:
    """Sáng 8h: gửi tóm tắt lịch hôm nay cho mọi approved user."""
    if _bot is None:
        return
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(UserApproval).where(UserApproval.status == "approved")
        )
        users = list(result.scalars().all())

        now = datetime.now(timezone.utc)
        end_today = now.replace(hour=23, minute=59, second=59)

        for u in users:
            try:
                sched_result = await session.execute(
                    select(Schedule)
                    .where(
                        Schedule.user_id == u.user_id,
                        Schedule.scheduled_at >= now,
                        Schedule.scheduled_at <= end_today,
                    )
                    .order_by(Schedule.scheduled_at)
                )
                today_scheds = list(sched_result.scalars().all())

                if not today_scheds:
                    continue  # Skip — không có lịch hôm nay

                lines = [f"🌅 *Chào buổi sáng đại hiệp* — {now.astimezone(TZ).strftime('%d/%m/%Y')}\n"]
                lines.append(f"📅 *Lịch hôm nay* ({len(today_scheds)}):")
                for s in today_scheds:
                    local = s.scheduled_at.astimezone(TZ).strftime("%H:%M")
                    desc = f" — {s.description}" if s.description else ""
                    lines.append(f"  • {local} *{s.title}*{desc}")

                text = "\n".join(lines)
                try:
                    await _bot.send_message(chat_id=u.user_id, text=text, parse_mode="Markdown")
                except Exception:
                    await _bot.send_message(chat_id=u.user_id, text=text)
                logger.info(f"Daily digest sent to {u.user_id}")
            except Exception as e:
                logger.error(f"Daily digest failed for {u.user_id}: {e}")


async def weekly_knowledge_digest() -> None:
    """Chủ nhật 9h sáng: phân tích entries tuần qua → 3 câu hỏi + 2 cảnh báo + 1 gợi ý.
    Chỉ gửi cho user có entries trong 7 ngày qua + có Gemini key.
    """
    if _bot is None:
        return
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(UserApproval).where(UserApproval.status == "approved")
        )
        users = list(result.scalars().all())

        for u in users:
            try:
                entries = await knowledge_repo.recent_entries(session, u.user_id, days=7)
                if not entries:
                    continue  # skip nếu tuần qua user không nhập gì

                gemini_key, _, _ = await keys_repo.get_decrypted_keys(session, u.user_id)
                if not gemini_key:
                    logger.info(f"Weekly digest skip {u.user_id}: no gemini key")
                    continue

                digest = await generate_digest(gemini_key, entries)
                if not digest:
                    continue

                header = f"🗓️ *Weekly Knowledge Digest* — {len(entries)} entries tuần qua\n\n"
                text = header + digest
                # Telegram message limit 4096
                if len(text) > 4000:
                    text = text[:4000] + "\n…(truncated)"
                try:
                    await _bot.send_message(chat_id=u.user_id, text=text, parse_mode="Markdown")
                except Exception:
                    await _bot.send_message(chat_id=u.user_id, text=text)
                logger.info(f"Weekly knowledge digest sent to {u.user_id} ({len(entries)} entries)")
            except Exception as e:
                logger.error(f"Weekly digest failed for {u.user_id}: {e}", exc_info=True)
