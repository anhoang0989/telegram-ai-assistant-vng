"""
Commands:
  /start       — đăng ký (nhập email/domain → chờ admin duyệt)
  /help        — hướng dẫn
  /setkey      — hiện 2 nút chọn loại key
  /mykey       — xem trạng thái keys
  /removekey   — xoá keys
  /status      — xem quota còn lại
  /cancel      — huỷ flow đang chờ input
  /pending     — (admin) xem user đang chờ duyệt
"""
import logging
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import user_keys as keys_repo
from src.db.repositories import approvals as appr_repo
from src.db.models import UserApproval
from src.ai.quota_tracker import quota_tracker
from src.db.repositories import notes as notes_repo
from src.db.repositories import schedules as sched_repo
from src.db.repositories import tasks as tasks_repo
from src.bot.keyboards import (
    approval_keyboard,
    setkey_keyboard,
    persistent_menu,
    schedules_list_keyboard,
    notes_root_keyboard,
    task_done_keyboard,
    PAGE_SIZE,
)

logger = logging.getLogger(__name__)


WELCOME_TEXT = (
    "🙏 Xin chào đại hiệp, tại hạ là trợ lý AI phục vụ đại hiệp trong giang hồ vận hành game.\n\n"
    "Để bắt đầu, xin đại hiệp gửi *Domain* (mã nhân viên VNG) của mình trong tin nhắn tiếp theo "
    "(vd: `AnH`, `TuVH`).\n\n"
    "Tại hạ sẽ chuyển yêu cầu tới admin để duyệt."
)

APPROVED_TEXT = (
    "✅ Đại hiệp đã được duyệt từ trước.\n\n"
    "Chọn loại API key muốn nhập:"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    # Admin luôn được bypass
    if user_id == settings.admin_user_id:
        await update.message.reply_text(
            "👑 Chào admin. Gõ /pending để xem các yêu cầu chờ duyệt, /members để quản lý user.\n"
            "Gõ /help để xem đầy đủ lệnh.",
            reply_markup=persistent_menu(is_admin=True),
        )
        return

    async with AsyncSessionFactory() as session:
        row = await appr_repo.get(session, user_id)

    if row and row.status == "approved":
        await update.message.reply_text(APPROVED_TEXT, reply_markup=setkey_keyboard())
        await update.message.reply_text(
            "📋 Menu nhanh ở góc dưới.",
            reply_markup=persistent_menu(is_admin=(user_id == settings.admin_user_id)),
        )
        return

    if row and row.status == "pending":
        await update.message.reply_text(
            "⏳ Yêu cầu của đại hiệp (`"
            + (row.email_or_domain or "")
            + "`) đang chờ tại hạ duyệt.\n"
            "Muốn đổi Domain? Cứ gửi Domain mới vào tin nhắn tiếp theo.",
            parse_mode="Markdown",
        )
        context.user_data["awaiting_email"] = True
        return

    if row and row.status == "rejected":
        await update.message.reply_text(
            "⛔ Yêu cầu trước đây của đại hiệp đã bị từ chối.\n"
            "Đại hiệp có thể thử lại bằng cách gửi Domain khác."
        )
        context.user_data["awaiting_email"] = True
        return

    # First time
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")
    context.user_data["awaiting_email"] = True


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    is_admin = update.effective_user.id == settings.admin_user_id
    base = (
        "📖 *Lệnh*\n\n"
        "• `/start` — đăng ký / bắt đầu\n"
        "• `/setkey` — hiện nút nhập key (Gemini/Groq)\n"
        "• `/mykey` — xem trạng thái keys\n"
        "• `/removekey` — xoá keys\n"
        "• `/status` — xem quota còn lại hôm nay\n"
        "• `/cancel` — huỷ flow đang chờ input\n\n"
        "Ngoài ra đại hiệp cứ chat tự nhiên, tại hạ sẽ tự hiểu ý.\n\n"
        "⚠️ *Bảo mật:* keys được mã hoá Fernet khi lưu. Nên nhắn key trong chat riêng."
    )
    if is_admin:
        base += "\n\n👑 *Lệnh admin:*\n• `/pending` — danh sách yêu cầu chờ duyệt"
    await update.message.reply_text(base, parse_mode="Markdown")


async def setkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔑 Đại hiệp chọn loại key cần nhập:",
        reply_markup=setkey_keyboard(),
    )


async def mykey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        gemini, groq = await keys_repo.get_decrypted_keys(session, user_id)

    def _mask(k: str | None) -> str:
        if not k:
            return "❌ chưa setup"
        return f"✅ `{k[:6]}...{k[-4:]}`"

    await update.message.reply_text(
        "🔑 *API keys của đại hiệp:*\n\n"
        f"• Gemini: {_mask(gemini)}\n"
        f"• Groq: {_mask(groq)}\n\n"
        "Thiếu key nào? Gõ /setkey để nhập.",
        parse_mode="Markdown",
    )


async def removekey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        removed = await keys_repo.remove(session, user_id)
    if removed:
        await update.message.reply_text("🗑️ Tại hạ đã xoá toàn bộ keys của đại hiệp. Muốn dùng lại thì /setkey.")
    else:
        await update.message.reply_text("Đại hiệp chưa có key nào để xoá.")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("awaiting_key", None)
    context.user_data.pop("awaiting_email", None)
    await update.message.reply_text("🚫 Đã huỷ flow đang chờ input.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
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
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def members_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != settings.admin_user_id:
        await update.message.reply_text("⛔ Chỉ admin.")
        return
    from src.bot.keyboards import members_list_keyboard
    async with AsyncSessionFactory() as session:
        members = await appr_repo.list_approved(session)
    if not members:
        await update.message.reply_text("👑 Chưa có member nào được duyệt.")
        return
    total_pages = (len(members) + PAGE_SIZE - 1) // PAGE_SIZE
    await update.message.reply_text(
        f"👑 Members ({len(members)}, trang 1/{total_pages})",
        reply_markup=members_list_keyboard(members, 0, total_pages),
    )


async def listmodels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin only — list Gemini models thực tế từ API để biết tên API ID đúng."""
    if update.effective_user.id != settings.admin_user_id:
        await update.message.reply_text("⛔ Chỉ admin.")
        return
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        gemini_key, _ = await keys_repo.get_decrypted_keys(session, user_id)
    if not gemini_key:
        await update.message.reply_text("⚠️ Admin chưa setup Gemini key. Gõ /setkey trước.")
        return
    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
        models = []
        for m in client.models.list():
            name = m.name.replace("models/", "")
            if "gemini" in name.lower():
                models.append(name)
        text = "📋 *Gemini models:*\n" + "\n".join(f"• `{m}`" for m in sorted(models)[:40])
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def schedules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        items = await sched_repo.get_upcoming(session, user_id, days_ahead=365)
    if not items:
        await update.message.reply_text("📅 Đại hiệp chưa có lịch nào sắp tới.")
        return
    total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    await update.message.reply_text(
        f"📅 *Lịch sắp tới của đại hiệp* ({len(items)} mục, trang 1/{total_pages})",
        parse_mode="Markdown",
        reply_markup=schedules_list_keyboard(items, 0, total_pages),
    )


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending tasks. Mỗi task có button 'Done'."""
    from zoneinfo import ZoneInfo
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        pending = await tasks_repo.list_filtered(session, user_id, "pending", limit=20)
        overdue = await tasks_repo.list_filtered(session, user_id, "overdue", limit=10)
    if not pending and not overdue:
        await update.message.reply_text("✅ Đại hiệp không có task nào pending. Trống tâm thanh thản.")
        return
    tz = ZoneInfo(settings.scheduler_timezone)
    lines = []
    if overdue:
        lines.append(f"🔥 *Quá hạn* ({len(overdue)}):")
        for t in overdue:
            d = t.deadline.astimezone(tz).strftime("%d/%m %H:%M") if t.deadline else "—"
            lines.append(f"  • #{t.id} [{d}] {t.title}")
        lines.append("")
    if pending:
        lines.append(f"📋 *Pending* ({len(pending)}):")
        for t in pending[:15]:
            d = t.deadline.astimezone(tz).strftime("%d/%m %H:%M") if t.deadline else "—"
            lines.append(f"  • #{t.id} [{d}] {t.title}")
    text = "\n".join(lines)
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(text)
    # Action buttons cho 5 task pending đầu tiên
    for t in pending[:5]:
        await update.message.reply_text(
            f"#{t.id} — {t.title}",
            reply_markup=task_done_keyboard(t.id),
        )


async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📝 *Note của đại hiệp*\n\nXem theo:",
        parse_mode="Markdown",
        reply_markup=notes_root_keyboard(),
    )


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != settings.admin_user_id:
        await update.message.reply_text("⛔ Chỉ admin dùng được lệnh này.")
        return

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(UserApproval).where(UserApproval.status == "pending").order_by(UserApproval.created_at)
        )
        rows = list(result.scalars().all())

    if not rows:
        await update.message.reply_text("✅ Không có yêu cầu nào đang chờ duyệt.")
        return

    await update.message.reply_text(f"📋 *{len(rows)} yêu cầu đang chờ:*", parse_mode="Markdown")
    for r in rows:
        uname = f"@{r.username}" if r.username else "(no username)"
        text = (
            f"👤 *{r.full_name or 'Không rõ tên'}* {uname}\n"
            f"🆔 Telegram ID: `{r.user_id}`\n"
            f"🏷️ Domain: `{r.email_or_domain}`\n"
            f"🕐 {r.created_at.strftime('%d/%m/%Y %H:%M')}"
        )
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=approval_keyboard(r.user_id)
        )
