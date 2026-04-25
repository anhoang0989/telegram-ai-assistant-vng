from sqlalchemy import select, or_, func, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Note


async def create(
    session: AsyncSession,
    user_id: int,
    title: str,
    content: str,
    topic: str | None = None,
    tags: list[str] | None = None,
    source: str = "chat",
) -> Note:
    note = Note(
        user_id=user_id,
        topic=topic,
        title=title,
        content=content,
        tags=tags or [],
        source=source,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


async def list_topics(session: AsyncSession, user_id: int) -> list[tuple[str, int]]:
    """Returns list of (topic_name, count) ordered by most recent activity."""
    result = await session.execute(
        select(Note.topic, func.count(Note.id), func.max(Note.created_at).label("last"))
        .where(Note.user_id == user_id, Note.topic.isnot(None))
        .group_by(Note.topic)
        .order_by(func.max(Note.created_at).desc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def list_by_topic(session: AsyncSession, user_id: int, topic: str) -> list[Note]:
    result = await session.execute(
        select(Note)
        .where(Note.user_id == user_id, Note.topic == topic)
        .order_by(Note.created_at.desc())
    )
    return list(result.scalars().all())


async def list_dates(session: AsyncSession, user_id: int) -> list[tuple[str, int]]:
    """Returns list of (date_str 'YYYY-MM-DD', count) ordered desc."""
    result = await session.execute(
        select(
            func.to_char(Note.created_at, "YYYY-MM-DD").label("d"),
            func.count(Note.id),
        )
        .where(Note.user_id == user_id)
        .group_by("d")
        .order_by(func.max(Note.created_at).desc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def list_by_date(session: AsyncSession, user_id: int, date_str: str) -> list[Note]:
    result = await session.execute(
        select(Note)
        .where(
            Note.user_id == user_id,
            func.to_char(Note.created_at, "YYYY-MM-DD") == date_str,
        )
        .order_by(Note.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_topic(session: AsyncSession, user_id: int, topic: str) -> int:
    result = await session.execute(
        sql_delete(Note).where(Note.user_id == user_id, Note.topic == topic)
    )
    await session.commit()
    return result.rowcount or 0


async def list_all(session: AsyncSession, user_id: int, limit: int = 20) -> list[Note]:
    result = await session.execute(
        select(Note)
        .where(Note.user_id == user_id)
        .order_by(Note.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def search(session: AsyncSession, user_id: int, query: str) -> list[Note]:
    q = f"%{query}%"
    result = await session.execute(
        select(Note)
        .where(Note.user_id == user_id, or_(Note.title.ilike(q), Note.content.ilike(q)))
        .order_by(Note.created_at.desc())
        .limit(10)
    )
    return list(result.scalars().all())


async def delete(session: AsyncSession, user_id: int, note_id: int) -> bool:
    note = await session.get(Note, note_id)
    if note and note.user_id == user_id:
        await session.delete(note)
        await session.commit()
        return True
    return False
