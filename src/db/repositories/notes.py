from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Note


async def create(
    session: AsyncSession,
    user_id: int,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source: str = "chat",
) -> Note:
    note = Note(user_id=user_id, title=title, content=content, tags=tags or [], source=source)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


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
