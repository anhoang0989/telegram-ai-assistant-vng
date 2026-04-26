"""
Inline button callbacks dispatcher.

Schedule drafts:    cs / xs
Note drafts:        cn / xn / pt / pts / ptn
List schedules:     ls / vs / ds
List notes:         ln / lnt / lnd / vt / vd / dt / dtc / dn
Approval:           approve / reject
Setkey:             setkey
Start menu:         sm:<action>  (sch/nte/knw/key/sta/mdl/hlp)
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import approvals as appr_repo
from src.db.repositories import notes as notes_repo
from src.db.repositories import schedules as sched_repo
from src.db.repositories import knowledge as knowledge_repo
from src.services import note_service, schedule_service
from src.bot import drafts
from src.ai.quota_tracker import quota_tracker
from src.bot.keyboards import (
    setkey_keyboard,
    approval_keyboard,
    persistent_menu,
    start_menu_keyboard,
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
    members_list_keyboard,
    member_detail_keyboard,
    confirm_delete_member_keyboard,
    model_picker_keyboard,
    knowledge_confirm_keyboard,
    knowledge_root_keyboard,
    knowledge_categories_for_product_keyboard,
    knowledge_entries_keyboard,
    knowledge_entry_detail_keyboard,
    knowledge_delete_confirm_keyboard,
    CATEGORY_LABELS,
    PROD_ALL,
    PROD_GEN,
    CAT_ALL,
    PAGE_SIZE,
)

logger = logging.getLogger(__name__)


async def _safe_edit(query, text: str, reply_markup=None, parse_mode: str | None = "Markdown") -> None:
    """Edit message với fallback plain-text khi Markdown parse fail."""
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if parse_mode:
            try:
                await query.edit_message_text(text, reply_markup=reply_markup)
                return
            except Exception:
                pass
        logger.warning(f"edit_message_text failed: {e}")


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
        elif head == "mb":
            await _members_list(update, context, int(parts[1]))
        elif head == "vm":
            await _view_member(update, context, int(parts[1]))
        elif head == "rv":
            await _revoke_member(update, context, int(parts[1]))
        elif head == "dm":
            await _confirm_delete_member(update, context, int(parts[1]))
        elif head == "dmc":
            await _delete_member(update, context, int(parts[1]))
        elif head == "sn":
            await _snooze_reminder(update, context, int(parts[1]), int(parts[2]))
        elif head == "mdl":
            await _set_preferred_model(update, context, parts[1] if len(parts) > 1 else "auto")
        elif head == "noop":
            pass  # decorative separator buttons in model picker
        elif head == "ck":
            await _confirm_knowledge(update, context, parts[1])
        elif head == "xk":
            await _cancel_knowledge_draft(update, context, parts[1])
        elif head == "kpe":
            await _edit_knowledge_product(update, context, parts[1])
        elif head == "kc":
            await _knowledge_root(update, context)
        elif head == "kpr":
            await _knowledge_view_product(update, context, parts[1])
        elif head == "klp":
            # data: "klp:<prod>:<cat>:<page>"
            full = data.split(":", 3)
            prod_token = full[1] if len(full) > 1 else PROD_ALL
            cat = full[2] if len(full) > 2 else CAT_ALL
            page = int(full[3]) if len(full) > 3 else 0
            await _knowledge_list(update, context, prod_token, cat, page)
        elif head == "kve":
            await _knowledge_view_entry(update, context, int(parts[1]))
        elif head == "kdl":
            await _knowledge_confirm_delete(update, context, int(parts[1]))
        elif head == "kdc":
            await _knowledge_delete(update, context, int(parts[1]))
        elif head == "kme":
            await _move_entry_product(update, context, int(parts[1]))
        elif head == "sm":
            await _start_menu_action(update, context, parts[1] if len(parts) > 1 else "")
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
                reply_markup=persistent_menu(is_admin=(target_user_id == settings.admin_user_id)),
            )
        else:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="⛔ Rất tiếc, yêu cầu của đại hiệp đã bị từ chối.",
            )
    except Exception as e:
        logger.error(f"Failed to notify user {target_user_id}: {e}")


_PROVIDER_INFO = {
    "gemini": ("Gemini", "https://aistudio.google.com/apikey"),
    "groq":   ("Groq",   "https://console.groq.com/keys"),
    "claude": ("Claude", "https://console.anthropic.com/settings/keys"),
}


async def _handle_setkey(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    query = update.callback_query
    _, provider = data.split(":", 1)
    if provider not in _PROVIDER_INFO:
        return
    context.user_data["awaiting_key"] = provider
    label, link = _PROVIDER_INFO[provider]
    extra = ""
    if provider == "claude":
        extra = "\n\n⚠️ Claude là API trả phí (Anthropic). Đại hiệp tự nạp credit trong console."
    await query.edit_message_text(
        f"🔑 Đại hiệp vui lòng paste {label} key vào tin nhắn tiếp theo.\n\n"
        f"Lấy key tại: {link}{extra}\n\nGõ /cancel để huỷ.",
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
    await _safe_edit(
        update.callback_query,
        f"📁 Topic: *{topic}*\n📝 *{draft['title']}*\n\n{draft['content']}\n\nDuyệt?",
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
    await _safe_edit(
        update.callback_query,
        f"📁 Topic: *{suggested}*\n📝 *{draft['title']}*\n\n{draft['content']}\n\nDuyệt?",
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
    await _safe_edit(
        update.callback_query,
        f"📅 *Lịch sắp tới của đại hiệp* ({len(items)} mục, trang {page + 1}/{total_pages})",
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
    await _safe_edit(
        update.callback_query,
        f"📌 *{s.title}*\n🕐 {local}\n🔁 {s.recurrence}{desc}",
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
    await _safe_edit(
        update.callback_query,
        "📝 *Note của đại hiệp*\n\nXem theo:",
        reply_markup=notes_root_keyboard(),
    )


async def _notes_by_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        topics = await notes_repo.list_topics(session, user_id)
    if not topics:
        await update.callback_query.edit_message_text("📁 Đại hiệp chưa có topic nào.")
        return
    await _safe_edit(
        update.callback_query,
        f"📁 *Topics* ({len(topics)})",
        reply_markup=topics_list_keyboard(topics),
    )


async def _notes_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        dates = await notes_repo.list_dates(session, user_id)
    if not dates:
        await update.callback_query.edit_message_text("📅 Đại hiệp chưa có note nào.")
        return
    await _safe_edit(
        update.callback_query,
        f"📅 *Note theo ngày* ({len(dates)} ngày)",
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
        await _safe_edit(update.callback_query, f"📁 Topic *{topic}* trống.")
        return
    lines = [f"📁 *{topic}* ({len(notes)} notes)\n"]
    for i, n in enumerate(notes[:10], 1):
        lines.append(f"{i}. *{n.title}* — {n.content[:80]}")
    await _safe_edit(
        update.callback_query,
        "\n".join(lines),
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
    await _safe_edit(
        update.callback_query,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _confirm_delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_hash: str) -> None:
    topic = drafts.resolve_topic_hash(topic_hash)
    if not topic:
        await update.callback_query.edit_message_text("⚠️ Topic không hợp lệ.")
        return
    await _safe_edit(
        update.callback_query,
        f"⚠️ Xoá luôn cả topic *{topic}* và TẤT CẢ note bên trong?",
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
    await _safe_edit(update.callback_query, f"🗑️ Đã xoá topic *{topic}* ({n} notes).")


async def _delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE, note_id: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        ok = await notes_repo.delete(session, user_id, note_id)
    if ok:
        await update.callback_query.edit_message_text("🗑️ Đã xoá note.")
    else:
        await update.callback_query.edit_message_text("❌ Không xoá được.")


# ============ ADMIN MEMBERS ============

def _admin_only(update: Update) -> bool:
    return update.effective_user.id == settings.admin_user_id


async def _members_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    if not _admin_only(update):
        await update.callback_query.edit_message_text("⛔ Chỉ admin.")
        return
    async with AsyncSessionFactory() as session:
        members = await appr_repo.list_approved(session)
    if not members:
        await update.callback_query.edit_message_text("👑 Chưa có member nào được duyệt.")
        return
    total_pages = (len(members) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    await update.callback_query.edit_message_text(
        f"👑 Members ({len(members)}, trang {page + 1}/{total_pages})",
        reply_markup=members_list_keyboard(members, page, total_pages),
    )


async def _view_member(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int) -> None:
    if not _admin_only(update):
        await update.callback_query.edit_message_text("⛔ Chỉ admin.")
        return
    async with AsyncSessionFactory() as session:
        row = await appr_repo.get(session, target_id)
        if not row:
            await update.callback_query.edit_message_text("❌ Không tìm thấy member.")
            return
        stats = await appr_repo.user_stats(session, target_id)
    uname = f"@{row.username}" if row.username else "(no username)"
    text = (
        f"👤 {row.full_name or 'Không rõ'} {uname}\n"
        f"🆔 {row.user_id}\n"
        f"🏷️ Domain: {row.email_or_domain}\n"
        f"📅 Trạng thái: {row.status}\n"
        f"━━━━━━━━━━\n"
        f"📊 Thống kê:\n"
        f"• Lịch sắp tới: {stats['upcoming_schedules']}\n"
        f"• Note: {stats['note_count']} (trong {stats['topic_count']} topic)\n"
        f"• Knowledge: {stats.get('knowledge_count', 0)}\n"
        f"• Meeting: {stats['meeting_count']}\n"
        f"• Tin nhắn: {stats['msg_count']}"
    )
    await update.callback_query.edit_message_text(
        text, reply_markup=member_detail_keyboard(target_id)
    )


async def _revoke_member(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int) -> None:
    if not _admin_only(update):
        await update.callback_query.edit_message_text("⛔ Chỉ admin.")
        return
    if target_id == settings.admin_user_id:
        await update.callback_query.edit_message_text("⛔ Không thể revoke admin.")
        return
    async with AsyncSessionFactory() as session:
        await appr_repo.set_status(session, target_id, "rejected")
    await _safe_edit(
        update.callback_query,
        f"⛔ Đã revoke user `{target_id}`. Data vẫn được giữ.",
    )
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="⚠️ Quyền sử dụng bot của đại hiệp đã bị admin thu hồi.",
        )
    except Exception:
        pass


async def _confirm_delete_member(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int) -> None:
    if not _admin_only(update):
        await update.callback_query.edit_message_text("⛔ Chỉ admin.")
        return
    if target_id == settings.admin_user_id:
        await update.callback_query.edit_message_text("⛔ Không thể xoá admin.")
        return
    await _safe_edit(
        update.callback_query,
        f"⚠️ Xác nhận XOÁ user `{target_id}` và TOÀN BỘ data (note, lịch, meeting, conversation, key)?\n"
        f"Hành động không thể hoàn tác.",
        reply_markup=confirm_delete_member_keyboard(target_id),
    )


# ============ SNOOZE + TASKS ============

async def _snooze_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE, schedule_id: int, minutes: int) -> None:
    """Tạo Schedule mới offset N phút từ now để reminder fire lại."""
    from datetime import datetime, timedelta, timezone
    from src.db.models import Schedule
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        original = await session.get(Schedule, schedule_id)
        if not original or original.user_id != user_id:
            await update.callback_query.edit_message_text("⚠️ Không tìm thấy lịch gốc để snooze.")
            return
        new_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        new_sched = Schedule(
            user_id=user_id,
            title=f"⏸ Snooze: {original.title}",
            description=f"Snooze {minutes}p từ lịch #{original.id}",
            scheduled_at=new_at,
            recurrence="none",
        )
        session.add(new_sched)
        await session.commit()
    await _safe_edit(
        update.callback_query,
        f"⏸ Đã snooze *{minutes} phút*. Tại hạ sẽ nhắc lại sau.",
    )


# ============ ADMIN: delete member ============

async def _delete_member(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int) -> None:
    if not _admin_only(update):
        await update.callback_query.edit_message_text("⛔ Chỉ admin.")
        return
    if target_id == settings.admin_user_id:
        await update.callback_query.edit_message_text("⛔ Không thể xoá admin.")
        return
    async with AsyncSessionFactory() as session:
        counts = await appr_repo.delete_user_data(session, target_id)
    summary = ", ".join(f"{k}={v}" for k, v in counts.items())
    await _safe_edit(
        update.callback_query,
        f"🗑️ Đã xoá user `{target_id}`.\n{summary}",
    )


# ============ MODEL SELECTOR ============

# Whitelist các model_id được phép pin — match với llm_tier1..tier9 + 'auto'
def _allowed_models() -> set[str]:
    return {
        "auto",
        settings.llm_tier1, settings.llm_tier2, settings.llm_tier3,
        settings.llm_tier4, settings.llm_tier5, settings.llm_tier6,
        settings.llm_tier7, settings.llm_tier8, settings.llm_tier9,
    }


# ============ KNOWLEDGE BASE ============

def _resolve_prod_token(token: str) -> tuple[str, str | None, str | None]:
    """Resolve callback prod token → (display_label, repo_filter, real_product_name).
    repo_filter: None=all, '_general_'=NULL, or actual product name.
    real_product_name: None for sentinels, else product string.
    """
    if token == PROD_ALL:
        return ("📚 Tất cả product", None, None)
    if token == PROD_GEN:
        return ("🌐 General", knowledge_repo.GENERAL_SENTINEL, None)
    real = drafts.resolve_product_hash(token)
    if real is None:
        return (f"⚠️ Unknown product", None, None)
    return (f"🎮 {real}", real, real)


def _entry_prod_token(entry) -> str:
    """Build prod_token để navigate back từ entry detail."""
    if entry.product is None:
        return PROD_GEN
    return drafts.hash_product(entry.product)


async def _confirm_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    user_id = update.effective_user.id
    draft = drafts.get_knowledge_draft(user_id)
    if not draft or draft["draft_id"] != draft_id:
        await update.callback_query.edit_message_text("⚠️ Draft đã hết hạn.")
        return
    async with AsyncSessionFactory() as session:
        entry = await knowledge_repo.create(
            session,
            user_id=user_id,
            product=draft.get("product"),
            category=draft["category"],
            title=draft["title"],
            content=draft["content"],
            tags=draft.get("tags"),
        )
    drafts.pop_knowledge_draft(user_id)
    cat_label = CATEGORY_LABELS.get(entry.category, entry.category)
    prod_label = f"🎮 {entry.product}" if entry.product else "🌐 General"
    await update.callback_query.edit_message_text(
        f"✅ Đã lưu vào kho:\n{prod_label} | {cat_label}\n📝 {entry.title}"
    )


async def _cancel_knowledge_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    user_id = update.effective_user.id
    drafts.pop_knowledge_draft(user_id)
    context.user_data.pop("awaiting_knowledge_product", None)
    await update.callback_query.edit_message_text("🚫 Đã hủy draft knowledge.")


async def _edit_knowledge_product(update: Update, context: ContextTypes.DEFAULT_TYPE, draft_id: str) -> None:
    user_id = update.effective_user.id
    draft = drafts.get_knowledge_draft(user_id)
    if not draft or draft["draft_id"] != draft_id:
        await update.callback_query.edit_message_text("⚠️ Draft đã hết hạn.")
        return
    context.user_data["awaiting_knowledge_product"] = draft_id
    cur = draft.get("product") or "(General/none)"
    await update.callback_query.edit_message_text(
        f"✏️ Product hiện tại: *{cur}*\n\n"
        "Gõ tên product mới (vd: `JX1`, `JX2`, `VLTKM`).\n"
        "Gõ `_general_` hoặc `none` nếu data chung không gắn product.\n"
        "Gõ /cancel để huỷ.",
        parse_mode="Markdown",
    )


async def _knowledge_root(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        products = await knowledge_repo.list_products(session, user_id)
    if not products:
        await update.callback_query.edit_message_text("📚 Kho tri thức đang trống.")
        return
    total = sum(c for _, c in products)
    await _safe_edit(
        update.callback_query,
        f"📚 *Kho tri thức* — {total} entries / {len(products)} product\n\nChọn product:",
        reply_markup=knowledge_root_keyboard(products),
    )


async def _knowledge_view_product(update: Update, context: ContextTypes.DEFAULT_TYPE, prod_token: str) -> None:
    user_id = update.effective_user.id
    label, repo_filter, _real = _resolve_prod_token(prod_token)
    async with AsyncSessionFactory() as session:
        cats = await knowledge_repo.list_categories_for_product(
            session, user_id, product=repo_filter,
        )
    if not cats:
        await update.callback_query.edit_message_text(f"{label}: trống.")
        return
    total = sum(c for _, c in cats)
    await _safe_edit(
        update.callback_query,
        f"{label} — {total} entries trong {len(cats)} category\n\nChọn category:",
        reply_markup=knowledge_categories_for_product_keyboard(prod_token, cats),
    )


async def _knowledge_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    prod_token: str, cat: str, page: int,
) -> None:
    user_id = update.effective_user.id
    prod_label, repo_prod, _ = _resolve_prod_token(prod_token)
    cat_filter = None if cat == CAT_ALL else cat
    async with AsyncSessionFactory() as session:
        entries = await knowledge_repo.list_filtered(
            session, user_id=user_id, product=repo_prod, category=cat_filter, limit=200,
        )
    if not entries:
        await update.callback_query.edit_message_text(f"{prod_label}: category này trống.")
        return
    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    cat_label = CATEGORY_LABELS.get(cat, "📚 Tất cả category") if cat != CAT_ALL else "📚 Tất cả category"
    await _safe_edit(
        update.callback_query,
        f"{prod_label} / {cat_label} — {len(entries)} entries (trang {page + 1}/{total_pages})",
        reply_markup=knowledge_entries_keyboard(entries, prod_token, cat, page, total_pages),
    )


async def _knowledge_view_entry(update: Update, context: ContextTypes.DEFAULT_TYPE, entry_id: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        entry = await knowledge_repo.get(session, user_id, entry_id)
    if not entry:
        await update.callback_query.edit_message_text("❌ Entry không tồn tại.")
        return
    cat_label = CATEGORY_LABELS.get(entry.category, entry.category)
    prod_label = f"🎮 {entry.product}" if entry.product else "🌐 General"
    tags_line = (" 🏷️ " + ", ".join(entry.tags)) if entry.tags else ""
    body = entry.content[:1500]
    if len(entry.content) > 1500:
        body += "\n…(truncated)"
    text = (
        f"{prod_label} | {cat_label}\n📝 *{entry.title}*{tags_line}\n"
        f"🕐 {entry.updated_at.strftime('%d/%m/%Y %H:%M')}\n\n"
        f"{body}"
    )
    prod_token = _entry_prod_token(entry)
    await _safe_edit(
        update.callback_query,
        text,
        reply_markup=knowledge_entry_detail_keyboard(entry.id, prod_token, entry.category),
    )


async def _knowledge_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, entry_id: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        entry = await knowledge_repo.get(session, user_id, entry_id)
    if not entry:
        await update.callback_query.edit_message_text("❌ Entry không tồn tại.")
        return
    prod_token = _entry_prod_token(entry)
    await _safe_edit(
        update.callback_query,
        f"⚠️ Xoá entry *{entry.title}*?",
        reply_markup=knowledge_delete_confirm_keyboard(entry.id, prod_token, entry.category),
    )


async def _knowledge_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, entry_id: int) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        ok = await knowledge_repo.delete(session, user_id, entry_id)
    if ok:
        await update.callback_query.edit_message_text("🗑️ Đã xoá entry.")
    else:
        await update.callback_query.edit_message_text("❌ Không xoá được.")


async def _move_entry_product(update: Update, context: ContextTypes.DEFAULT_TYPE, entry_id: int) -> None:
    """Cho user đổi product của entry sau khi đã lưu (vd entries v0.9.0 chưa có product)."""
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        entry = await knowledge_repo.get(session, user_id, entry_id)
    if not entry:
        await update.callback_query.edit_message_text("❌ Entry không tồn tại.")
        return
    context.user_data["awaiting_move_entry_product"] = entry_id
    cur = entry.product or "(General/none)"
    await update.callback_query.edit_message_text(
        f"📂 Entry hiện ở product: *{cur}*\n📝 {entry.title}\n\n"
        "Gõ tên product mới (vd: `JX1`, `JX2`).\n"
        "Gõ `_general_` hoặc `none` để chuyển sang General.\n"
        "Gõ /cancel để huỷ.",
        parse_mode="Markdown",
    )


async def _set_preferred_model(update: Update, context: ContextTypes.DEFAULT_TYPE, model: str) -> None:
    user_id = update.effective_user.id
    if model not in _allowed_models():
        await update.callback_query.edit_message_text(f"⚠️ Model không hợp lệ: `{model}`")
        return
    async with AsyncSessionFactory() as session:
        await appr_repo.set_preferred_model(session, user_id, model)
    label = "🤖 Auto (smart routing)" if model == "auto" else f"📌 `{model}` (pinned)"
    await _safe_edit(
        update.callback_query,
        f"✅ Đã đổi model:\n\n{label}\n\nGõ /model để đổi tiếp, hoặc cứ chat bình thường.",
        reply_markup=model_picker_keyboard(model),
    )


# ============ START MENU ============

async def _start_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """Handle sm:* callbacks from the compact /start inline menu."""
    query = update.callback_query
    user_id = update.effective_user.id

    if action == "sch":
        async with AsyncSessionFactory() as session:
            items = await sched_repo.get_upcoming(session, user_id, days_ahead=365)
        if not items:
            await query.message.reply_text("📅 Đại hiệp chưa có lịch nào sắp tới.")
            return
        total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
        await query.message.reply_text(
            f"📅 *Lịch sắp tới* ({len(items)} mục, trang 1/{total_pages})",
            parse_mode="Markdown",
            reply_markup=schedules_list_keyboard(items, 0, total_pages),
        )

    elif action == "nte":
        await query.message.reply_text(
            "📝 *Note của đại hiệp*\n\nXem theo:",
            parse_mode="Markdown",
            reply_markup=notes_root_keyboard(),
        )

    elif action == "knw":
        async with AsyncSessionFactory() as session:
            products = await knowledge_repo.list_products(session, user_id)
        if not products:
            await query.message.reply_text(
                "📚 Kho tri thức đang trống.\n"
                "Chat để thêm data/design/insight, vd: \"Lưu data JX1 ARPU tháng 4: 45k\"."
            )
            return
        total = sum(c for _, c in products)
        await query.message.reply_text(
            f"📚 *Kho tri thức* — {total} entries / {len(products)} product\n\nChọn product:",
            parse_mode="Markdown",
            reply_markup=knowledge_root_keyboard(products),
        )

    elif action == "key":
        await query.message.reply_text(
            "🔑 Chọn loại key muốn nhập:",
            reply_markup=setkey_keyboard(),
        )

    elif action == "sta":
        status = quota_tracker.status(user_id)
        tier_labels = {0: "T1 Flash Lite", 1: "T2 Flash", 2: "T3 Pro", 3: "T4 Groq"}
        lines = ["📊 *Quota của đại hiệp hôm nay:*\n"]
        for i, (model, s) in enumerate(status.items()):
            label = tier_labels.get(i, model)
            rpm_bar = "🟢" if s["rpm_used"] < s["rpm_limit"] * 0.8 else "🟡" if s["rpm_used"] < s["rpm_limit"] else "🔴"
            rpd_bar = "🟢" if s["rpd_used"] < s["rpd_limit"] * 0.8 else "🟡" if s["rpd_used"] < s["rpd_limit"] else "🔴"
            lines.append(
                f"{rpm_bar} *{label}*\n"
                f"  RPM: {s['rpm_used']}/{s['rpm_limit']} | RPD: {s['rpd_used']}/{s['rpd_limit']} {rpd_bar}"
            )
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif action == "mdl":
        async with AsyncSessionFactory() as session:
            current = await appr_repo.get_preferred_model(session, user_id)
        label = "🤖 Auto" if current == "auto" else f"📌 `{current}`"
        await query.message.reply_text(
            f"🧠 *Chọn model AI:*\n\nHiện đang dùng: {label}\n\n"
            "• *Auto* — tự chọn tier rẻ nhất + fallback khi hết quota\n"
            "• *Pin model cụ thể* — luôn dùng model đó, không fallback",
            parse_mode="Markdown",
            reply_markup=model_picker_keyboard(current),
        )

    elif action == "hlp":
        await query.message.reply_text("📖 Gõ /help để xem hướng dẫn đầy đủ.")
