from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repositories import notes as repo
from src.db.models import Note


async def save_note(
    session: AsyncSession,
    user_id: int,
    title: str,
    content: str,
    topic: str | None = None,
    tags: list[str] | None = None,
    source: str = "chat",
) -> Note:
    return await repo.create(
        session,
        user_id=user_id,
        title=title,
        content=content,
        topic=topic,
        tags=tags,
        source=source,
    )
