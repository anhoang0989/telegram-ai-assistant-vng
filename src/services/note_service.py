from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repositories import notes as repo
from src.db.models import Note


async def save_note(session: AsyncSession, title: str, content: str, tags: list[str] | None = None, source: str = "chat") -> Note:
    return await repo.create(session, title=title, content=content, tags=tags, source=source)


async def list_notes(session: AsyncSession) -> str:
    notes = await repo.list_all(session)
    if not notes:
        return "📝 Chưa có ghi chú nào."
    lines = [f"📝 *Danh sách ghi chú ({len(notes)} ghi chú):*\n"]
    for n in notes:
        tags_str = f" `{'` `'.join(n.tags)}`" if n.tags else ""
        lines.append(f"• [{n.id}] *{n.title}*{tags_str}\n  _{n.created_at.strftime('%d/%m/%Y %H:%M')}_")
    return "\n".join(lines)


async def search_notes(session: AsyncSession, query: str) -> str:
    notes = await repo.search(session, query)
    if not notes:
        return f"🔍 Không tìm thấy ghi chú nào với từ khoá `{query}`."
    lines = [f"🔍 *Kết quả tìm kiếm '{query}':*\n"]
    for n in notes:
        lines.append(f"• [{n.id}] *{n.title}*\n  {n.content[:100]}{'...' if len(n.content) > 100 else ''}")
    return "\n".join(lines)


async def export_notes(session: AsyncSession) -> str:
    notes = await repo.list_all(session, limit=200)
    if not notes:
        return "Chưa có ghi chú nào."
    parts = []
    for n in notes:
        parts.append(f"# [{n.id}] {n.title}\nTags: {', '.join(n.tags or [])}\nDate: {n.created_at.strftime('%d/%m/%Y %H:%M')}\n\n{n.content}\n")
    return "\n---\n".join(parts)
