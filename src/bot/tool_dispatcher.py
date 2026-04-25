"""
Dispatch tool calls → services. All calls scoped per user_id (multi-tenant).
Returns STRUCTURED dict so the LLM can feed-back to build natural responses.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo
from src.config import settings
from datetime import timedelta
from src.services import note_service, schedule_service
from src.db.repositories import notes as notes_repo, schedules as sched_repo
from src.db.repositories import user_keys as keys_repo
from src.db.repositories import knowledge as knowledge_repo
from src.db.models import MeetingMinute, Schedule
from src.bot import drafts
from src.ai.providers import gemini_web_search

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.scheduler_timezone)


async def dispatch_tool(
    session: AsyncSession,
    user_id: int,
    tool_name: str,
    tool_input: dict,
) -> dict:
    try:
        if tool_name == "web_search":
            query = tool_input.get("query", "").strip()
            if not query:
                return {"ok": False, "error": "Empty query"}
            gemini_key, _, _ = await keys_repo.get_decrypted_keys(session, user_id)
            if not gemini_key:
                return {"ok": False, "error": "Chưa có Gemini key để search"}
            result = await gemini_web_search(gemini_key, query)
            return {
                "ok": True,
                "query": query,
                "text": result["text"],
                "sources": result["sources"],
                "instruction": (
                    "Đây là kết quả search real-time. Hãy tổng hợp lại bằng tiếng Việt, "
                    "ngắn gọn, trích dẫn nguồn nếu có. KHÔNG bịa thêm số liệu ngoài kết quả này."
                ),
            }

        elif tool_name == "save_note":
            # Không insert ngay — tạo draft, chat_handler sẽ show keyboard pick-topic + confirm
            draft_id = drafts.put_note_draft(
                user_id=user_id,
                title=tool_input["title"],
                content=tool_input["content"],
                suggested_topic=tool_input.get("topic"),
            )
            return {
                "ok": True,
                "draft": True,
                "draft_id": draft_id,
                "title": tool_input["title"],
                "suggested_topic": tool_input.get("topic"),
                "instruction": (
                    "Đã chuẩn bị note draft. KHÔNG gọi thêm tool. "
                    "Báo cho user biết tại hạ đã chuẩn bị note, đại hiệp pick topic + duyệt qua nút bên dưới."
                ),
            }

        elif tool_name == "search_notes":
            notes = await notes_repo.search(session, user_id, tool_input["query"])
            return {
                "ok": True,
                "count": len(notes),
                "results": [
                    {
                        "id": n.id,
                        "title": n.title,
                        "content": n.content,
                        "tags": n.tags or [],
                        "created_at": n.created_at.strftime("%d/%m/%Y %H:%M"),
                    }
                    for n in notes
                ],
            }

        elif tool_name == "list_notes":
            limit = tool_input.get("limit", 10)
            notes = await notes_repo.list_all(session, user_id, limit=limit)
            return {
                "ok": True,
                "count": len(notes),
                "results": [
                    {
                        "id": n.id,
                        "title": n.title,
                        "tags": n.tags or [],
                        "created_at": n.created_at.strftime("%d/%m/%Y %H:%M"),
                    }
                    for n in notes
                ],
            }

        elif tool_name == "create_schedule":
            # Không insert ngay — tạo draft, chat_handler sẽ show confirm keyboard
            draft_id = drafts.put_schedule_draft(
                user_id=user_id,
                title=tool_input["title"],
                scheduled_at=tool_input["scheduled_at"],
                description=tool_input.get("description"),
                recurrence=tool_input.get("recurrence", "none"),
            )
            # Parse preview time
            try:
                from datetime import datetime as _dt
                preview_dt = _dt.fromisoformat(tool_input["scheduled_at"])
                if preview_dt.tzinfo is None:
                    preview_dt = preview_dt.replace(tzinfo=TZ)
                preview = preview_dt.astimezone(TZ).strftime("%d/%m/%Y %H:%M")
            except Exception:
                preview = tool_input["scheduled_at"]
            return {
                "ok": True,
                "draft": True,
                "draft_id": draft_id,
                "title": tool_input["title"],
                "scheduled_at_local": preview,
                "instruction": (
                    "Đã chuẩn bị lịch draft. KHÔNG gọi thêm tool. "
                    "Báo cho user biết lịch đã chuẩn bị, đại hiệp duyệt qua nút bên dưới."
                ),
            }

        elif tool_name == "list_schedules":
            days = tool_input.get("days_ahead", 7)
            schedules = await sched_repo.get_upcoming(session, user_id, days_ahead=days)
            return {
                "ok": True,
                "count": len(schedules),
                "results": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "description": s.description,
                        "scheduled_at_local": s.scheduled_at.astimezone(TZ).strftime("%d/%m/%Y %H:%M"),
                        "recurrence": s.recurrence,
                    }
                    for s in schedules
                ],
            }

        elif tool_name == "delete_schedule":
            deleted = await sched_repo.delete(session, user_id, tool_input["schedule_id"])
            return {"ok": deleted, "id": tool_input["schedule_id"]}

        elif tool_name == "create_offset_reminder":
            ref_id = tool_input["reference_schedule_id"]
            minutes_before = int(tool_input["minutes_before"])
            label = tool_input.get("label")
            ref = await session.get(Schedule, ref_id)
            if not ref or ref.user_id != user_id:
                return {"ok": False, "error": f"Reference schedule {ref_id} không tồn tại"}
            new_at = ref.scheduled_at - timedelta(minutes=minutes_before)
            sign = "trước" if minutes_before >= 0 else "sau"
            mins_abs = abs(minutes_before)
            new_title = label or f"⏰ {mins_abs}p {sign}: {ref.title}"
            new_sched = Schedule(
                user_id=user_id,
                title=new_title,
                description=f"Reminder offset từ '{ref.title}' (lịch #{ref.id})",
                scheduled_at=new_at,
                recurrence="none",
            )
            session.add(new_sched)
            await session.commit()
            await session.refresh(new_sched)
            return {
                "ok": True,
                "id": new_sched.id,
                "title": new_sched.title,
                "scheduled_at_local": new_at.astimezone(TZ).strftime("%d/%m/%Y %H:%M"),
                "reference_id": ref_id,
            }

        elif tool_name == "save_meeting_summary":
            meeting = MeetingMinute(
                user_id=user_id,
                title=tool_input["title"],
                raw_input=tool_input["raw_input"],
                summary=tool_input["summary"],
                action_items=tool_input.get("action_items", []),
                recommendations=tool_input.get("recommendations", []),
            )
            if tool_input.get("counterarguments"):
                meeting.recommendations = {
                    "recommendations": tool_input.get("recommendations", []),
                    "counterarguments": tool_input["counterarguments"],
                }
            session.add(meeting)
            await session.commit()
            await session.refresh(meeting)
            return {
                "ok": True,
                "id": meeting.id,
                "title": meeting.title,
                "action_items_count": len(tool_input.get("action_items", []) or []),
            }

        elif tool_name == "save_knowledge":
            # Không insert ngay — tạo draft, chat handler sẽ show confirm keyboard
            category = knowledge_repo.normalize_category(tool_input.get("category"))
            product = knowledge_repo.normalize_product(tool_input.get("product"))
            # Cross-reference: tìm 5 entries gần nhất cùng (product, category) để
            # user review trước khi save (phát hiện duplicate/conflict thủ công).
            product_filter = (
                knowledge_repo.GENERAL_SENTINEL if product is None else product
            )
            related_entries = await knowledge_repo.list_filtered(
                session,
                user_id=user_id,
                product=product_filter,
                category=category,
                limit=5,
            )
            related = [
                {"id": e.id, "title": e.title}
                for e in related_entries
            ]
            draft_id = drafts.put_knowledge_draft(
                user_id=user_id,
                category=category,
                title=tool_input["title"],
                content=tool_input["content"],
                tags=tool_input.get("tags"),
                product=product,
                related=related,
            )
            return {
                "ok": True,
                "draft": True,
                "draft_id": draft_id,
                "product": product,
                "category": category,
                "title": tool_input["title"],
                "related_count": len(related),
                "instruction": (
                    "Đã chuẩn bị knowledge draft. KHÔNG gọi thêm tool. "
                    "Báo user biết tại hạ đã chuẩn bị entry kèm product+category. "
                    "Nếu có related_count > 0 → mention với user 'có N entry liên quan trong cùng product+category, đại hiệp xem preview để tránh duplicate'. "
                    "User duyệt qua nút bên dưới (có nút đổi product nếu sai)."
                ),
            }

        elif tool_name == "search_knowledge":
            query = tool_input.get("query", "").strip()
            if not query:
                return {"ok": False, "error": "Empty query"}
            entries = await knowledge_repo.search(
                session,
                user_id=user_id,
                query=query,
                product=tool_input.get("product"),
                category=tool_input.get("category"),
                limit=tool_input.get("limit", 5),
            )
            return {
                "ok": True,
                "count": len(entries),
                "filter_product": tool_input.get("product"),
                "filter_category": tool_input.get("category"),
                "results": [
                    {
                        "id": e.id,
                        "product": e.product,
                        "category": e.category,
                        "title": e.title,
                        "content": e.content[:1500],
                        "tags": e.tags or [],
                        "updated_at": e.updated_at.strftime("%d/%m/%Y %H:%M"),
                    }
                    for e in entries
                ],
                "instruction": (
                    "Đây là kết quả từ kho tri thức cá nhân của user (đã filter product+category nếu có). "
                    "Dùng để phân tích / phản biện / trả lời. "
                    "Nếu count=0 → nói thẳng kho chưa có data, đề nghị user nhập, mention rõ product nếu đã filter."
                ),
            }

        elif tool_name == "list_knowledge":
            entries = await knowledge_repo.list_filtered(
                session,
                user_id=user_id,
                product=tool_input.get("product"),
                category=tool_input.get("category"),
                limit=tool_input.get("limit", 10),
            )
            products = await knowledge_repo.list_products(session, user_id)
            return {
                "ok": True,
                "count": len(entries),
                "products_overview": [
                    {"product": (p or "_general_"), "count": n} for p, n in products
                ],
                "results": [
                    {
                        "id": e.id,
                        "product": e.product,
                        "category": e.category,
                        "title": e.title,
                        "tags": e.tags or [],
                        "updated_at": e.updated_at.strftime("%d/%m/%Y %H:%M"),
                    }
                    for e in entries
                ],
            }

        elif tool_name == "list_meetings":
            limit = tool_input.get("limit", 10)
            result = await session.execute(
                select(MeetingMinute)
                .where(MeetingMinute.user_id == user_id)
                .order_by(MeetingMinute.created_at.desc())
                .limit(limit)
            )
            meetings = list(result.scalars().all())
            return {
                "ok": True,
                "count": len(meetings),
                "results": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "summary": m.summary,
                        "created_at": m.created_at.strftime("%d/%m/%Y %H:%M"),
                    }
                    for m in meetings
                ],
            }

        else:
            logger.warning(f"Unknown tool: {tool_name}")
            return {"ok": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error(f"Tool dispatch error [{tool_name}]: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}
