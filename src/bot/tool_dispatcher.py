"""
Dispatch tool calls → services. All calls scoped per user_id (multi-tenant).
Returns STRUCTURED dict so the LLM can feed-back to build natural responses.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo
from src.config import settings
from src.services import note_service, schedule_service
from src.db.repositories import notes as notes_repo, schedules as sched_repo
from src.db.models import MeetingMinute
from src.bot import drafts

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.scheduler_timezone)


async def dispatch_tool(
    session: AsyncSession,
    user_id: int,
    tool_name: str,
    tool_input: dict,
) -> dict:
    try:
        if tool_name == "save_note":
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
            return {"ok": True, "id": meeting.id, "title": meeting.title}

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
