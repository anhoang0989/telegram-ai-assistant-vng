"""
Knowledge base CRUD — personal store cho data/design/behavior/research per user.
Search dùng ILIKE trên title + content (đủ cho ~vài trăm entries).
Upgrade lên tsvector / pgvector khi cần.
"""
from sqlalchemy import select, func, or_, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import KnowledgeEntry

VALID_CATEGORIES = {
    "game_data",      # số liệu game (ARPU, retention, DAU…)
    "design",         # design doc, system spec
    "user_behavior",  # insight từ social, survey, review
    "market",         # research thị trường, đối thủ
    "meeting_log",    # ghi chú meeting đã chốt
    "other",
}


def normalize_category(cat: str | None) -> str:
    if not cat:
        return "other"
    cat = cat.strip().lower().replace(" ", "_").replace("-", "_")
    return cat if cat in VALID_CATEGORIES else "other"


async def create(
    session: AsyncSession,
    user_id: int,
    category: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source: str = "chat",
) -> KnowledgeEntry:
    entry = KnowledgeEntry(
        user_id=user_id,
        category=normalize_category(category),
        title=title[:255],
        content=content,
        tags=tags or None,
        source=source,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def search(
    session: AsyncSession,
    user_id: int,
    query: str,
    category: str | None = None,
    limit: int = 5,
) -> list[KnowledgeEntry]:
    """ILIKE trên title + content. Optional filter theo category."""
    pat = f"%{query.strip()}%"
    stmt = select(KnowledgeEntry).where(
        KnowledgeEntry.user_id == user_id,
        or_(
            KnowledgeEntry.title.ilike(pat),
            KnowledgeEntry.content.ilike(pat),
        ),
    )
    if category:
        stmt = stmt.where(KnowledgeEntry.category == normalize_category(category))
    stmt = stmt.order_by(KnowledgeEntry.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_by_category(
    session: AsyncSession,
    user_id: int,
    category: str | None = None,
    limit: int = 10,
) -> list[KnowledgeEntry]:
    stmt = select(KnowledgeEntry).where(KnowledgeEntry.user_id == user_id)
    if category:
        stmt = stmt.where(KnowledgeEntry.category == normalize_category(category))
    stmt = stmt.order_by(KnowledgeEntry.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_categories(session: AsyncSession, user_id: int) -> list[tuple[str, int]]:
    """Trả về [(category, count), ...] sort by count desc."""
    result = await session.execute(
        select(KnowledgeEntry.category, func.count(KnowledgeEntry.id))
        .where(KnowledgeEntry.user_id == user_id)
        .group_by(KnowledgeEntry.category)
        .order_by(func.count(KnowledgeEntry.id).desc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def get(session: AsyncSession, user_id: int, entry_id: int) -> KnowledgeEntry | None:
    entry = await session.get(KnowledgeEntry, entry_id)
    if entry is None or entry.user_id != user_id:
        return None
    return entry


async def delete(session: AsyncSession, user_id: int, entry_id: int) -> bool:
    entry = await get(session, user_id, entry_id)
    if entry is None:
        return False
    await session.delete(entry)
    await session.commit()
    return True


async def delete_all_for_user(session: AsyncSession, user_id: int) -> int:
    """Cascade — gọi từ delete_user_data trong approvals.py."""
    r = await session.execute(
        sql_delete(KnowledgeEntry).where(KnowledgeEntry.user_id == user_id)
    )
    return r.rowcount or 0
