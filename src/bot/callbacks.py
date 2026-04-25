"""
Inline button callbacks dispatcher.

Schedule drafts:    cs / xs
Note drafts:        cn / xn / pt / pts / ptn
List schedules:     ls / vs / ds
List notes:         ln / lnt / lnd / vt / vd / dt / dtc / dn
Approval:           approve / reject
Setkey:             setkey
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import approvals as appr_repo
from src.db.repositories import notes as notes_repo
from src.db.repositories import schedules as sched_repo
from src.services import note_service, schedule_service
from src.bot import drafts
from src.bot.keyboards import (
    setkey_keyboard,
    approval_keyboard,
    persistent_menu,
    schedule_confirm_keyboard,
    schedules_list_keyboard,
    schedule_detail_keyboard,
    note_topic_picker,
    note_confirm_keyboard,
    notes_root_keyboard,
    topics_list_keyboard,
    dates_list_keyboard,
    topic_detail_keyboard,
    confirm_delete_topic_keyboard,
    PAGE_SIZE,
)

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
    parts = data.split(":", 2)
    head = parts[0]

    try:
        if head in ("approve", "reject"):
            await _handle_approval(update, context, data)
        elif head == "setkey":
            await _handle_setkey(update, context, data)
        elif head == "cs":
            await _confirm_schedule(update, context, parts[1])
        elif head == "xs":
            await _cancel_schedule_draft(update, context, parts[1])
        elif head == "cn":
            await _confirm_note(update, context, parts[1])
        elif head == "xn":
            await _cancel_note_draft(update, context, parts[1])
        elif head == "pt":
            await _pick_topic(update, context, parts[1], parts[2])
        elif head == "pts":
            await _pick_suggested_topic(update, context, parts[1])
        elif head == "ptn":
            await _pick_new_topic(update, context, parts[1])
        elif head == "ls":
            await _list_schedules(update, context, int(parts[1]))
        elif head == "vs":
            await _view_schedule(update, context, int(parts[1]))
        elif head == "ds":
            await _delete_schedule(update, context, int(parts[1]))
        elif head == "ln":
            await _notes_root(update, context)
        elif head == "lnt":
            await _notes_by_topic(update, context)
        elif head == "lnd":
            await _notes_by_date(update, context)
        elif head == "vt":
            await _view_topic(update, context, parts[1])
        elif head == "vd":
            await _view_date(update, context, parts[1])
        elif head == "dt":
            await _confirm_delete_topic(update, context, parts[1])
        elif head == "dtc":
            await _delete_topic(update, context, parts[1])
        elif head == "dn":
            await _delete_note(update, context, int(parts[1]))
        else:
            logger.warning(f"Unknown callback data: {data}")
    except Exception as e:
        logger.error(f"Callback error [{data}]: {e}", exc_info=True)
        try:
            await query.edit_message_text(f"⚠️ Lỗi: {e}")
        except Exception:
            pass


# ============ APPROVAL ============

async def _handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    query = update.callback_query
    actor = update.effective_user

    if actor.id != settings.admin_user_id:
        await query.edit_message_text("⛔ Chỉ admin mới được duyệt.")
        return

    action, user_id_str = data.split(":", 1)
    target_user_id = int(user_id_str)
    new_status = "approved" if action == "approve" else "rejected"

    async with AsyncSessionFactory() as session:
        row = await appr_repo.set_status(session, target_user_id, new_status)

    if row is None:
        await query.edit_message_text("❌ Không tìm thấy yêu cầu này.")
        return

    verb = "✅ Đã duyệt" if new_status == "approved" else "❌ Đã từ chối"
    original = query.message.text or ""
    await query.edit_message_text(f"{original}\n\n━━━━━\n{verb} bởi admin.")

    try:
        if new_status == "approved":
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "🎉 Đại hiệp đã được tại hạ duyệt!\n\n"
                    "Bước tiếp theo — setup API keys cá nhân (miễn phí):\n"
                    "🔹 Gemini: https://aistudio.google.com/apikey\n"
                    "🔹 Groq: https://console.groq.com/keys\n\n"
                    "Chọn loại key muốn nhập:"
                ),
                reply_markup=setkey_keyboard(),
                disable_web_page_preview=True,
            )
            await context.bot.send_message(
                chat_id=target_user_id,
                text="📋 Menu nhanh đã sẵn sàng ở góc dưới.",
                reply_markup=persistent_menu(),
            )
        else:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="⛔ Rất tiếc, yêu cầu của đại hiệp đã bị từ chối.",
            )
    except Exception as e:
        logger.error(f"Failed to notify user {target_user_id}: {e}")


async def _handle_setkey(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    query = update.callback_query
    _, provider = data.split(":", 1)
    if provider not in ("gemini", "groq"):
        return
    context.user_data["awaiting_key"] = provider
    label = "Gemini" if provider == "gemini" else "Groq"
    link = "https://aistudio.google.com/apikey" if provider == "gemini" else "https://console.groq.com/keys"
    await query.edit_message_text(
        f"🔑 Đại hiệp vui lòng paste {label} key vào tin nhắn tiếp theo.\n\n"
        f"Lấy key tại: {link}\n\nGõ /cancel để huỷ.",
        disable_web_page_preview=True,
    )


# ============ SCHEDULE DRAFT ============

async def _confirm_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    draft = drafts.get_schedule_draft(user_id)
    if not draft or draft["draft_id"] != draft_id:
        await query.edit_message_text("⚠️ Draft đã hết hạn hoặc không tồn tại.")
        return

    async with AsyncSessionFactory() as session:
        s = await schedule_service.create_schedule(
            session,
            user_id=user_id,
            title=draft["title"],
            scheduled_at_str=draft["scheduled_at"],
            description=draft["description"],
            recurrence=draft["recurrence"],
        )
    drafts.pop_schedule_draft(user_id)
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(settings.scheduler_timezone)
    local = s.scheduled_at.astimezone(tz).strftime("%d/%m/%Y %H:%M")
    await query.edit_message_text(f"✅ Đã lưu lịch:\n📌 {s.title}\n🕐 {local}")


async def _cancel_schedule_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    user_id = update.effective_user.id
    drafts.pop_schedule_draft(user_id)
    await update.callback_query.edit_message_text("🚫 Đã hủy draft lịch.")


# ============ NOTE DRAFT ============

async def _pick_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str, topic_hash: str) -> None:
    user_id = update.effective_user.id
    topic = drafts.resolve_topic_hash(topic_hash)
    if not topic:
        await update.callback_query.edit_message_text("⚠️ Topic không hợp lệ.")
        return
    draft = drafts.update_note_topic(user_id, topic)
    if not draft or draft["draft_id"] != draft_id:
        await update.callback_query.edit_message_text("⚠️ Draft hết hạn.")
        return
    await update.callback_query.edit_message_text(
        f"📁 Topic: *{topic}*\n📝 *{draft['title']}*\n\n{draft['content']}\n\nDuyệt?",
        parse_mode="Markdown",
        reply_markup=note_confirm_keyboard(draft_id),
    )


async def _pick_suggested_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    user_id = update.effective_user.id
    draft = drafts.get_note_draft(user_id)
    if not draft or draft["draft_id"] != draft_id:
        await update.callback_query.edit_message_text("⚠️ Draft hết hạn.")
        return
    suggested = draft.get("suggested_topic")
    if not suggested:
        await update.callback_query.edit_message_text("⚠️ Không có topic gợi ý.")
        return
    drafts.update_note_topic(user_id, suggested)
    await update.callback_query.edit_message_text(
        f"📁 Topic: *{suggested}*\n📝 *{draft['title']}*\n\n{draft['content']}\n\nDuyệt?",
        parse_mode="Markdown",
        reply_markup=note_confirm_keyboard(draft_id),
    )


async def _pick_new_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    context.user_data["awaiting_note_topic"] = draft_id
    await update.callback_query.edit_message_text(
        "✏️ Đại hiệp gõ tên topic mới (vd: 'Idea LiveOps Q3'):"
    )


async def _confirm_note(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    user_id = update.effective_user.id
    draft = drafts.get_note_draft(user_id)
    if not draft or draft["draft_id"] != draft_id:
        await update.callback_query.edit_message_text("⚠️ Draft hết hạn.")
        return
    if not draft.get("chosen_topic"):
        await update.callback_query.edit_message_text("⚠️ Đại hiệp chưa chọn topic.")
        return

    async with AsyncSessionFactory() as session:
        note = await note_service.save_note(
            session,
            user_id=user_id,
            title=draft["title"],
            content=draft["content"],
            topic=draft["chosen_topic"],
        )
    drafts.pop_note_draft(user_id)
    await update.callback_query.edit_message_text(
        f"✅ Đã lưu note:\n📁 {note.topic}\n📝 {note.title}"
    )


async def _cancel_note_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    user_id = update.effective_user.id
    drafts.pop_note_draft(user_id)
    context.user_data.pop("awaiting_note_topic", None)
    await update.callback_query.edit_message_text("🚫 Đã hủy draft note.")


# ============ LIST SCHEDULES ============

async def _list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        items = await sched_repo.get_upcoming(session, user_id, days_ahead=365)

    if not items:
        await update.callback_query.edit_message_text("📅 Đại hiệp chưa có lịch nào sắp tới.")
        return

    total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    await update.callback_query.edit_message_text(
        f"📅 *Lịch sắp tới của đại hiệp* ({len(items)} mục, trang {page + 1}/{total_pages})",
        parse_mode="Markdown",
        reply_markup=schedules_list_keyboard(items, page, total_pages),
    )


async def _view_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, schedule_id: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        from src.db.models import Schedule
        s = await session.get(Schedule, schedule_id)
        if not s or s.user_id != user_id:
            await update.callback_query.edit_message_text("❌ Lịch không tồn tại.")
            return
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(settings.scheduler_timezone)
    local = s.scheduled_at.astimezone(tz).strftime("%d/%m/%Y %H:%M")
    desc = f"\n\n_{s.description}_" if s.description else ""
    await update.callback_query.edit_message_text(
        f"📌 *{s.title}*\n🕐 {local}\n🔁 {s.recurrence}{desc}",
        parse_mode="Markdown",
        reply_markup=schedule_detail_keyboard(s.id),
    )


async def _delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, schedule_id: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        ok = await sched_repo.delete(session, user_id, schedule_id)
    if ok:
        await update.callback_query.edit_message_text("🗑️ Đã xoá lịch.")
    else:
        await update.callback_query.edit_message_text("❌ Không xoá được.")


# ============ LIST NOTES ============

async def _notes_root(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text(
        "📝 *Note của đại hiệp*\n\nXem theo:",
        parse_mode="Markdown",
        reply_markup=notes_root_keyboard(),
    )


async def _notes_by_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        topics = await notes_repo.list_topics(session, user_id)
    if not topics:
        await update.callback_query.edit_message_text("📁 Đại hiệp chưa có topic nào.")
        return
    await update.callback_query.edit_message_text(
        f"📁 *Topics* ({len(topics)})",
        parse_mode="Markdown",
        reply_markup=topics_list_keyboard(topics),
    )


async def _notes_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        dates = await notes_repo.list_dates(session, user_id)
    if not dates:
        await update.callback_query.edit_message_text("📅 Đại hiệp chưa có note nào.")
        return
    await update.callback_query.edit_message_text(
        f"📅 *Note theo ngày* ({len(dates)} ngày)",
        parse_mode="Markdown",
        reply_markup=dates_list_keyboard(dates),
    )


async def _view_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_hash: str) -> None:
    user_id = update.effective_user.id
    topic = drafts.resolve_topic_hash(topic_hash)
    if not topic:
        await update.callback_query.edit_message_text("⚠️ Topic không hợp lệ.")
        return
    async with AsyncSessionFactory() as session:
        notes = await notes_repo.list_by_topic(session, user_id, topic)
    if not notes:
        await update.callback_query.edit_message_text(f"📁 Topic *{topic}* trống.", parse_mode="Markdown")
        return
    lines = [f"📁 *{topic}* ({len(notes)} notes)\n"]
    for i, n in enumerate(notes[:10], 1):
        lines.append(f"{i}. *{n.title}* — {n.content[:80]}")
    await update.callback_query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=topic_detail_keyboard(topic_hash, notes),
    )


async def _view_date(update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        notes = await notes_repo.list_by_date(session, user_id, date_str)
    if not notes:
        await update.callback_query.edit_message_text(f"📅 {date_str}: trống.")
        return
    lines = [f"📅 *{date_str}* ({len(notes)} notes)\n"]
    for i, n in enumerate(notes[:15], 1):
        topic_label = f" [{n.topic}]" if n.topic else ""
        lines.append(f"{i}. *{n.title}*{topic_label}\n   {n.content[:100]}")
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton(f"🗑️ Xoá: {n.title[:40]}", callback_data=f"dn:{n.id}")] for n in notes[:10]]
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="lnd")])
    await update.callback_query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _confirm_delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_hash: str) -> None:
    topic = drafts.resolve_topic_hash(topic_hash)
    if not topic:
        await update.callback_query.edit_message_text("⚠️ Topic không hợp lệ.")
        return
    await update.callback_query.edit_message_text(
        f"⚠️ Xoá luôn cả topic *{topic}* và TẤT CẢ note bên trong?",
        parse_mode="Markdown",
        reply_markup=confirm_delete_topic_keyboard(topic_hash),
    )


async def _delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_hash: str) -> None:
    user_id = update.effective_user.id
    topic = drafts.resolve_topic_hash(topic_hash)
    if not topic:
        await update.callback_query.edit_message_text("⚠️ Topic không hợp lệ.")
        return
    async with AsyncSessionFactory() as session:
        n = await notes_repo.delete_topic(session, user_id, topic)
    await update.callback_query.edit_message_text(f"🗑️ Đã xoá topic *{topic}* ({n} notes).", parse_mode="Markdown")


async def _delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE, note_id: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        ok = await notes_repo.delete(session, user_id, note_id)
    if ok:
        await update.callback_query.edit_message_text("🗑️ Đã xoá note.")
    else:
        await update.callback_query.edit_message_text("❌ Không xoá được.")
