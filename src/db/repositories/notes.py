from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Note


async def create(session: AsyncSession, title: str, content: str, tags: list[str] | None = None, source: str = "chat") -> Note:
    note = Note(title=title, content=content, tags=tags or [], source=source)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


async def list_all(session: AsyncSession, limit: int = 20) -> list[Note]:
    result = await session.execute(
        select(Note).order_by(Note.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def search(session: AsyncSession, query: str) -> list[Note]:
    q = f"%{query}%"
    result = await session.execute(
        select(Note)
        .where(or_(Note.title.ilike(q), Note.content.ilike(q)))
        .order_by(Note.created_at.desc())
        .limit(10)
    )
    return list(result.scalars().all())


async def delete(session: AsyncSession, note_id: int) -> bool:
    note = await session.get(Note, note_id)
    if note:
        await session.delete(note)
        await session.commit()
        return True
    return False
