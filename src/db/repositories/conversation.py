from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Conversation


async def get_recent(session: AsyncSession, user_id: int, limit: int = 40) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return list(reversed(rows))


async def save(session: AsyncSession, user_id: int, role: str, content: str, tokens_used: int | None = None) -> None:
    session.add(Conversation(user_id=user_id, role=role, content=content, tokens_used=tokens_used))
    await session.commit()
