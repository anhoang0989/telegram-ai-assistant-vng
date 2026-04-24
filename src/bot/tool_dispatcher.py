"""
Dispatch tool calls → services. Trả về STRUCTURED dict để AI có thể feed-back làm response tự nhiên.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo
from src.config import settings
from src.services import note_service, schedule_service
from src.db.repositories import notes as notes_repo, schedules as sched_repo
from src.db.models import MeetingMinute

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.scheduler_timezone)


async def dispatch_tool(session: AsyncSession, tool_name: str, tool_input: dict) -> dict:
    """
    Execute a tool and return structured result.
    Return dict gets serialized to JSON and fed back to the LLM.
    """
    try:
        if tool_name == "save_note":
            note = await note_service.save_note(
                session,
                title=tool_input["title"],
                content=tool_input["content"],
                tags=tool_input.get("tags"),
            )
            return {"ok": True, "id": note.id, "title": note.title}

        elif tool_name == "search_notes":
            notes = await notes_repo.search(session, tool_input["query"])
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
            notes = await notes_repo.list_all(session, limit=limit)
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
            schedule = await schedule_service.create_schedule(
                session,
                title=tool_input["title"],
                scheduled_at_str=tool_input["scheduled_at"],
                description=tool_input.get("description"),
                recurrence=tool_input.get("recurrence", "none"),
            )
            local_dt = schedule.scheduled_at.astimezone(TZ)
            return {
                "ok": True,
                "id": schedule.id,
                "title": schedule.title,
                "scheduled_at_local": local_dt.strftime("%d/%m/%Y %H:%M"),
            }

        elif tool_name == "list_schedules":
            days = tool_input.get("days_ahead", 7)
            schedules = await sched_repo.get_upcoming(session, days_ahead=days)
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
            deleted = await sched_repo.delete(session, tool_input["schedule_id"])
            return {"ok": deleted, "id": tool_input["schedule_id"]}

        elif tool_name == "save_meeting_summary":
            meeting = MeetingMinute(
                title=tool_input["title"],
                raw_input=tool_input["raw_input"],
                summary=tool_input["summary"],
                action_items=tool_input.get("action_items", []),
                recommendations=tool_input.get("recommendations", []),
            )
            # Store counterarguments inside recommendations structure if provided
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
            from sqlalchemy import select
            limit = tool_input.get("limit", 10)
            result = await session.execute(
                select(MeetingMinute).order_by(MeetingMinute.created_at.desc()).limit(limit)
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
