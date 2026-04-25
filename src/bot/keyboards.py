"""
Tất cả InlineKeyboardMarkup + ReplyKeyboardMarkup builders.
Callback data convention (≤64 bytes):
  cs:<draft_id>      confirm schedule draft
  xs:<draft_id>      cancel schedule draft
  cn:<draft_id>      confirm note draft (after topic chosen)
  xn:<draft_id>      cancel note draft
  pt:<draft_id>:<topic_hash>   pick existing topic for note draft
  pts:<draft_id>     suggested topic
  ptn:<draft_id>     new topic (await text input)
  ls:<page>          list schedules pagination
  vs:<id>            view schedule detail
  ds:<id>            delete schedule
  ln                 notes root menu
  lnt                notes by topic
  lnd                notes by date
  vt:<topic_hash>    view topic
  dt:<topic_hash>    delete whole topic (confirm)
  dtc:<topic_hash>   confirm delete topic
  dn:<id>            delete single note
  sn:<sched_id>:<min>  snooze reminder N phút
  td:<task_id>       mark task done
  noop               no-op (placeholder)
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from src.bot import drafts

PAGE_SIZE = 5


def setkey_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 Nhập key Gemini", callback_data="setkey:gemini"),
            InlineKeyboardButton("🔑 Nhập key Groq", callback_data="setkey:groq"),
        ]
    ])


def approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"reject:{user_id}"),
        ]
    ])


def persistent_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Menu cố định ở góc dưới — luôn hiện sau khi user approved.
    Admin có thêm nút 👑 Members."""
    rows = [
        [KeyboardButton("📅 Lịch"), KeyboardButton("📝 Note")],
        [KeyboardButton("🔑 Key"), KeyboardButton("📊 Status")],
    ]
    if is_admin:
        rows.append([KeyboardButton("👑 Members")])
    rows.append([KeyboardButton("/start"), KeyboardButton("/help")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


# ============ SCHEDULE ============

def schedule_confirm_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Lưu lịch", callback_data=f"cs:{draft_id}"),
            InlineKeyboardButton("❌ Hủy", callback_data=f"xs:{draft_id}"),
        ]
    ])


def schedules_list_keyboard(schedules: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    start = page * PAGE_SIZE
    page_items = schedules[start:start + PAGE_SIZE]
    for s in page_items:
        from zoneinfo import ZoneInfo
        from src.config import settings
        tz = ZoneInfo(settings.scheduler_timezone)
        local = s.scheduled_at.astimezone(tz).strftime("%H:%M %d/%m")
        label = f"📌 {local} — {s.title[:40]}"
        rows.append([InlineKeyboardButton(label, callback_data=f"vs:{s.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"ls:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Sau ➡️", callback_data=f"ls:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows) if rows else InlineKeyboardMarkup([])


def schedule_detail_keyboard(schedule_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Xoá lịch", callback_data=f"ds:{schedule_id}"),
            InlineKeyboardButton("⬅️ Quay lại", callback_data="ls:0"),
        ]
    ])


# ============ NOTE ============

def note_topic_picker(draft_id: str, existing_topics: list[str], suggested: str | None) -> InlineKeyboardMarkup:
    rows = []
    if suggested:
        rows.append([InlineKeyboardButton(f"💡 Gợi ý: {suggested[:40]}", callback_data=f"pts:{draft_id}")])
    for t in existing_topics[:8]:  # tối đa 8 topic gần nhất
        h = drafts.hash_topic(t)
        rows.append([InlineKeyboardButton(f"📁 {t[:45]}", callback_data=f"pt:{draft_id}:{h}")])
    rows.append([InlineKeyboardButton("➕ Topic mới", callback_data=f"ptn:{draft_id}")])
    rows.append([InlineKeyboardButton("❌ Hủy note", callback_data=f"xn:{draft_id}")])
    return InlineKeyboardMarkup(rows)


def note_confirm_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Lưu note", callback_data=f"cn:{draft_id}"),
            InlineKeyboardButton("❌ Hủy", callback_data=f"xn:{draft_id}"),
        ]
    ])


def notes_root_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📁 Theo chủ đề", callback_data="lnt"),
            InlineKeyboardButton("📅 Theo ngày", callback_data="lnd"),
        ]
    ])


def topics_list_keyboard(topics: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    rows = []
    for topic, count in topics[:20]:
        h = drafts.hash_topic(topic)
        rows.append([InlineKeyboardButton(f"📁 {topic[:35]} ({count})", callback_data=f"vt:{h}")])
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="ln")])
    return InlineKeyboardMarkup(rows)


def dates_list_keyboard(dates: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    rows = []
    for d, count in dates[:20]:
        rows.append([InlineKeyboardButton(f"📅 {d} ({count})", callback_data=f"vd:{d}")])
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="ln")])
    return InlineKeyboardMarkup(rows)


def topic_detail_keyboard(topic_hash: str, notes: list) -> InlineKeyboardMarkup:
    rows = []
    for n in notes[:10]:
        rows.append([InlineKeyboardButton(f"🗑️ Xoá: {n.title[:45]}", callback_data=f"dn:{n.id}")])
    rows.append([InlineKeyboardButton("🗑️ XOÁ CẢ TOPIC", callback_data=f"dt:{topic_hash}")])
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="lnt")])
    return InlineKeyboardMarkup(rows)


# ============ ADMIN MEMBERS ============

def members_list_keyboard(members, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    start = page * PAGE_SIZE
    for m in members[start:start + PAGE_SIZE]:
        label = f"👤 {(m.full_name or m.email_or_domain or m.username or m.user_id)[:35]}"
        rows.append([InlineKeyboardButton(label, callback_data=f"vm:{m.user_id}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"mb:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Sau ➡️", callback_data=f"mb:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows)


def member_detail_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⛔ Revoke (giữ data)", callback_data=f"rv:{target_user_id}")],
        [InlineKeyboardButton("🗑️ XOÁ user + data", callback_data=f"dm:{target_user_id}")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="mb:0")],
    ])


def confirm_delete_member_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Xoá luôn", callback_data=f"dmc:{target_user_id}"),
            InlineKeyboardButton("❌ Không", callback_data=f"vm:{target_user_id}"),
        ]
    ])


def confirm_delete_topic_keyboard(topic_hash: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Xoá luôn", callback_data=f"dtc:{topic_hash}"),
            InlineKeyboardButton("❌ Không", callback_data=f"vt:{topic_hash}"),
        ]
    ])


def snooze_keyboard(schedule_id: int) -> InlineKeyboardMarkup:
    """Snooze reminder N phút (10 / 30 / 60)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸ 10p", callback_data=f"sn:{schedule_id}:10"),
            InlineKeyboardButton("⏸ 30p", callback_data=f"sn:{schedule_id}:30"),
            InlineKeyboardButton("⏸ 1h", callback_data=f"sn:{schedule_id}:60"),
        ]
    ])


def task_done_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done", callback_data=f"td:{task_id}")]
    ])
