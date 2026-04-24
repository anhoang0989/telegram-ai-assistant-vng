from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Schedule


async def create(
    session: AsyncSession,
    title: str,
    scheduled_at: datetime,
    description: str | None = None,
    recurrence: str = "none",
) -> Schedule:
    s = Schedule(title=title, scheduled_at=scheduled_at, description=description, recurrence=recurrence)
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s


async def get_upcoming(session: AsyncSession, days_ahead: int = 7) -> list[Schedule]:
    cutoff = datetime.utcnow() + timedelta(days=days_ahead)
    result = await session.execute(
        select(Schedule)
        .where(Schedule.scheduled_at >= datetime.utcnow(), Schedule.scheduled_at <= cutoff)
        .order_by(Schedule.scheduled_at)
    )
    return list(result.scalars().all())


async def get_pending_unnotified(session: AsyncSession) -> list[Schedule]:
    result = await session.execute(
        select(Schedule)
        .where(Schedule.notified == False, Schedule.scheduled_at <= datetime.utcnow())
    )
    return list(result.scalars().all())


async def mark_notified(session: AsyncSession, schedule_id: int) -> None:
    s = await session.get(Schedule, schedule_id)
    if s:
        s.notified = True
        await session.commit()


async def delete(session: AsyncSession, schedule_id: int) -> bool:
    s = await session.get(Schedule, schedule_id)
    if s:
        await session.delete(s)
        await session.commit()
        return True
    return False
