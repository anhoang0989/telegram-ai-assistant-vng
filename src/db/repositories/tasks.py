from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Task


async def create(
    session: AsyncSession,
    user_id: int,
    title: str,
    description: str | None = None,
    owner: str | None = None,
    deadline: datetime | None = None,
    source_meeting_id: int | None = None,
) -> Task:
    t = Task(
        user_id=user_id,
        title=title,
        description=description,
        owner=owner,
        deadline=deadline,
        source_meeting_id=source_meeting_id,
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


async def list_filtered(
    session: AsyncSession,
    user_id: int,
    filter_kind: str = "pending",
    limit: int = 50,
) -> list[Task]:
    """
    filter_kind:
      - pending  : done=False, sort theo deadline (NULL last)
      - overdue  : done=False, deadline < now
      - today    : done=False, deadline trong [now, end_of_day]
      - done     : done=True, mới nhất trước
      - all      : tất cả, mới nhất trước
    """
    now = datetime.now(timezone.utc)
    q = select(Task).where(Task.user_id == user_id)

    if filter_kind == "pending":
        q = q.where(Task.done == False).order_by(Task.deadline.asc().nulls_last(), Task.created_at.desc())
    elif filter_kind == "overdue":
        q = q.where(Task.done == False, Task.deadline.is_not(None), Task.deadline < now).order_by(Task.deadline.asc())
    elif filter_kind == "today":
        end_today = now.replace(hour=23, minute=59, second=59)
        q = q.where(
            Task.done == False,
            Task.deadline.is_not(None),
            Task.deadline >= now.replace(hour=0, minute=0, second=0),
            Task.deadline <= end_today,
        ).order_by(Task.deadline.asc())
    elif filter_kind == "done":
        q = q.where(Task.done == True).order_by(Task.updated_at.desc())
    else:
        q = q.order_by(Task.created_at.desc())

    q = q.limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def mark_done(session: AsyncSession, user_id: int, task_id: int) -> bool:
    t = await session.get(Task, task_id)
    if t and t.user_id == user_id:
        t.done = True
        await session.commit()
        return True
    return False


async def delete(session: AsyncSession, user_id: int, task_id: int) -> bool:
    t = await session.get(Task, task_id)
    if t and t.user_id == user_id:
        await session.delete(t)
        await session.commit()
        return True
    return False
