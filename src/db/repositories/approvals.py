from datetime import datetime
from sqlalchemy import select, func, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import (
    UserApproval, UserApiKey, Note, Schedule, Conversation, MeetingMinute,
)


async def get(session: AsyncSession, user_id: int) -> UserApproval | None:
    result = await session.execute(select(UserApproval).where(UserApproval.user_id == user_id))
    return result.scalar_one_or_none()


async def create_pending(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    full_name: str | None,
    email_or_domain: str,
) -> UserApproval:
    row = await get(session, user_id)
    if row is None:
        row = UserApproval(
            user_id=user_id,
            username=username,
            full_name=full_name,
            email_or_domain=email_or_domain,
            status="pending",
        )
        session.add(row)
    else:
        row.email_or_domain = email_or_domain
        row.username = username
        row.full_name = full_name
        row.status = "pending"
    await session.commit()
    await session.refresh(row)
    return row


async def set_status(session: AsyncSession, user_id: int, status: str) -> UserApproval | None:
    row = await get(session, user_id)
    if row:
        row.status = status
        await session.commit()
    return row


async def get_preferred_model(session: AsyncSession, user_id: int) -> str:
    """Trả về preferred_model. Default 'auto' nếu chưa có row."""
    row = await get(session, user_id)
    return (row.preferred_model if row and row.preferred_model else "auto")


async def set_preferred_model(session: AsyncSession, user_id: int, model: str) -> None:
    row = await get(session, user_id)
    if row is None:
        return
    row.preferred_model = model
    await session.commit()


async def is_approved(session: AsyncSession, user_id: int) -> bool:
    row = await get(session, user_id)
    return row is not None and row.status == "approved"


async def list_approved(session: AsyncSession) -> list[UserApproval]:
    result = await session.execute(
        select(UserApproval)
        .where(UserApproval.status == "approved")
        .order_by(UserApproval.updated_at.desc())
    )
    return list(result.scalars().all())


async def user_stats(session: AsyncSession, user_id: int) -> dict:
    """Count-only stats: upcoming_schedules, notes, topics, messages, meetings."""
    upcoming = (await session.execute(
        select(func.count(Schedule.id)).where(
            Schedule.user_id == user_id,
            Schedule.scheduled_at >= datetime.utcnow(),
        )
    )).scalar() or 0
    note_count = (await session.execute(
        select(func.count(Note.id)).where(Note.user_id == user_id)
    )).scalar() or 0
    topic_count = (await session.execute(
        select(func.count(func.distinct(Note.topic))).where(
            Note.user_id == user_id, Note.topic.isnot(None),
        )
    )).scalar() or 0
    msg_count = (await session.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
    )).scalar() or 0
    meeting_count = (await session.execute(
        select(func.count(MeetingMinute.id)).where(MeetingMinute.user_id == user_id)
    )).scalar() or 0
    return {
        "upcoming_schedules": upcoming,
        "note_count": note_count,
        "topic_count": topic_count,
        "msg_count": msg_count,
        "meeting_count": meeting_count,
    }


async def delete_user_data(session: AsyncSession, user_id: int) -> dict:
    """Hard delete user — approval + keys + notes + schedules + conversations + meetings."""
    counts = {}
    for model, label in [
        (Conversation, "conversations"),
        (Note, "notes"),
        (Schedule, "schedules"),
        (MeetingMinute, "meetings"),
    ]:
        r = await session.execute(sql_delete(model).where(model.user_id == user_id))
        counts[label] = r.rowcount or 0
    # User-keyed singletons (PK = user_id)
    r = await session.execute(sql_delete(UserApiKey).where(UserApiKey.user_id == user_id))
    counts["api_keys"] = r.rowcount or 0
    r = await session.execute(sql_delete(UserApproval).where(UserApproval.user_id == user_id))
    counts["approval"] = r.rowcount or 0
    await session.commit()
    return counts
