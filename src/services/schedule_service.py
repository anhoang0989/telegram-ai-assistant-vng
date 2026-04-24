from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repositories import schedules as repo
from src.db.models import Schedule
from src.config import settings

TZ = ZoneInfo(settings.scheduler_timezone)


def parse_iso(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


async def create_schedule(
    session: AsyncSession,
    user_id: int,
    title: str,
    scheduled_at_str: str,
    description: str | None = None,
    recurrence: str = "none",
) -> Schedule:
    scheduled_at = parse_iso(scheduled_at_str)
    return await repo.create(
        session,
        user_id=user_id,
        title=title,
        scheduled_at=scheduled_at,
        description=description,
        recurrence=recurrence,
    )


async def format_reminder(schedule: Schedule) -> str:
    local_dt = schedule.scheduled_at.astimezone(TZ)
    desc = f"\n_{schedule.description}_" if schedule.description else ""
    return f"⏰ *Nhắc nhở:* {schedule.title}{desc}\n🕐 {local_dt.strftime('%d/%m/%Y %H:%M')}"
