"""
Knowledge base CRUD — personal store cho data/design/behavior/research per user.
Phân vùng theo (product, category):
  - product: sản phẩm cụ thể (JX1, JX2...) hoặc NULL = General/cross-product
  - category: game_data | design | user_behavior | market | meeting_log | other

Search dùng ILIKE trên title + content (đủ cho ~vài trăm entries).
Sentinel cho product filter:
  None        → no filter (tất cả product)
  '_general_' → WHERE product IS NULL
  '<name>'    → WHERE product = '<name>' (exact match)
"""
import re
from sqlalchemy import select, func, or_, and_, delete as sql_delete
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

GENERAL_SENTINEL = "_general_"  # product=NULL filter
ALL_SENTINEL = "_all_"          # no filter

_PRODUCT_RE = re.compile(r"\s+")


def normalize_category(cat: str | None) -> str:
    if not cat:
        return "other"
    cat = cat.strip().lower().replace(" ", "_").replace("-", "_")
    return cat if cat in VALID_CATEGORIES else "other"


def normalize_product(product: str | None) -> str | None:
    """Trim + thay khoảng trắng thành '_'. Giữ case nguyên (JX1 ≠ jx1).
    Trả None nếu rỗng → general/cross-product.
    """
    if product is None:
        return None
    p = _PRODUCT_RE.sub("_", product.strip())
    p = p[:50]
    return p if p else None


async def create(
    session: AsyncSession,
    user_id: int,
    category: str,
    title: str,
    content: str,
    product: str | None = None,
    tags: list[str] | None = None,
    source: str = "chat",
) -> KnowledgeEntry:
    entry = KnowledgeEntry(
        user_id=user_id,
        product=normalize_product(product),
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


def _apply_product_filter(stmt, product: str | None):
    """Áp dụng product filter dựa trên sentinel.
    None hoặc '_all_' → không filter.
    '_general_' → WHERE product IS NULL.
    Khác → WHERE product = <name>.
    """
    if product is None or product == ALL_SENTINEL:
        return stmt
    if product == GENERAL_SENTINEL:
        return stmt.where(KnowledgeEntry.product.is_(None))
    return stmt.where(KnowledgeEntry.product == product)


def _apply_category_filter(stmt, category: str | None):
    if category is None or category == ALL_SENTINEL:
        return stmt
    return stmt.where(KnowledgeEntry.category == normalize_category(category))


async def search(
    session: AsyncSession,
    user_id: int,
    query: str,
    product: str | None = None,
    category: str | None = None,
    limit: int = 5,
) -> list[KnowledgeEntry]:
    """ILIKE trên title + content. Optional filter theo product + category."""
    pat = f"%{query.strip()}%"
    stmt = select(KnowledgeEntry).where(
        KnowledgeEntry.user_id == user_id,
        or_(
            KnowledgeEntry.title.ilike(pat),
            KnowledgeEntry.content.ilike(pat),
        ),
    )
    stmt = _apply_product_filter(stmt, product)
    stmt = _apply_category_filter(stmt, category)
    stmt = stmt.order_by(KnowledgeEntry.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_filtered(
    session: AsyncSession,
    user_id: int,
    product: str | None = None,
    category: str | None = None,
    limit: int = 200,
) -> list[KnowledgeEntry]:
    stmt = select(KnowledgeEntry).where(KnowledgeEntry.user_id == user_id)
    stmt = _apply_product_filter(stmt, product)
    stmt = _apply_category_filter(stmt, category)
    stmt = stmt.order_by(KnowledgeEntry.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_products(session: AsyncSession, user_id: int) -> list[tuple[str | None, int]]:
    """Trả [(product_name_or_None, count), ...] sort by count desc.
    None = general/cross-product entries.
    """
    result = await session.execute(
        select(KnowledgeEntry.product, func.count(KnowledgeEntry.id))
        .where(KnowledgeEntry.user_id == user_id)
        .group_by(KnowledgeEntry.product)
        .order_by(func.count(KnowledgeEntry.id).desc())
    )
    return [(row[0], row[1]) for row in result.all()]


async def list_categories_for_product(
    session: AsyncSession,
    user_id: int,
    product: str | None = None,
) -> list[tuple[str, int]]:
    """Trả [(category, count), ...] trong scope product (hoặc all nếu product=None/_all_)."""
    stmt = (
        select(KnowledgeEntry.category, func.count(KnowledgeEntry.id))
        .where(KnowledgeEntry.user_id == user_id)
    )
    stmt = _apply_product_filter(stmt, product)
    stmt = stmt.group_by(KnowledgeEntry.category).order_by(func.count(KnowledgeEntry.id).desc())
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def recent_entries(
    session: AsyncSession,
    user_id: int,
    days: int = 7,
    limit: int = 50,
) -> list[KnowledgeEntry]:
    """Entries created trong N ngày qua — dùng cho weekly digest."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(KnowledgeEntry)
        .where(
            KnowledgeEntry.user_id == user_id,
            KnowledgeEntry.created_at >= cutoff,
        )
        .order_by(KnowledgeEntry.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get(session: AsyncSession, user_id: int, entry_id: int) -> KnowledgeEntry | None:
    entry = await session.get(KnowledgeEntry, entry_id)
    if entry is None or entry.user_id != user_id:
        return None
    return entry


async def update_product(
    session: AsyncSession,
    user_id: int,
    entry_id: int,
    new_product: str | None,
) -> bool:
    """Đổi product của entry. None = move sang General."""
    entry = await get(session, user_id, entry_id)
    if entry is None:
        return False
    entry.product = normalize_product(new_product)
    await session.commit()
    return True


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
