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
from src.db.repositories import knowledge as knowledge_repo
from src.bot.keyboards import (
    approval_keyboard,
    setkey_keyboard,
    persistent_menu,
    start_menu_keyboard,
    schedules_list_keyboard,
    notes_root_keyboard,
    model_picker_keyboard,
    knowledge_root_keyboard,
    PAGE_SIZE,
)

logger = logging.getLogger(__name__)


WELCOME_TEXT = (
    "🙏 Xin chào! Tại hạ là trợ lý AI cá nhân.\n\n"
    "Gửi *Domain* (mã nhân viên VNG, vd: `AnH`) để đăng ký — admin sẽ duyệt sớm."
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    # Admin luôn được bypass
    if user_id == settings.admin_user_id:
        first_name = user.first_name or "Admin"
        await update.message.reply_text(
            f"👑 Chào {first_name}!",
            reply_markup=start_menu_keyboard(),
        )
        return

    async with AsyncSessionFactory() as session:
        row = await appr_repo.get(session, user_id)

    if row and row.status == "approved":
        first_name = user.first_name or "đại hiệp"
        await update.message.reply_text(
            f"👋 Chào {first_name}! Chọn chức năng:",
            reply_markup=start_menu_keyboard(),
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
        "📖 *Hướng dẫn dùng tại hạ*\n\n"
        "🙏 Tại hạ là trợ lý AI cá nhân của đại hiệp — giúp tra cứu, ghi chú, đặt lịch,"
        " tóm tắt họp, phân tích chiến lược ngành game.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🚀 *BẮT ĐẦU NHANH*\n"
        "1. Gõ `/start` để đăng ký (admin sẽ duyệt)\n"
        "2. Sau khi được duyệt, gõ `/setkey` nhập API key:\n"
        "   • *Gemini* (BẮT BUỘC, free): https://aistudio.google.com/apikey\n"
        "   • *Groq* (optional, free fallback): https://console.groq.com/keys\n"
        "   • *Claude* (optional, paid): https://console.anthropic.com/settings/keys\n"
        "3. Sau đó cứ chat tự nhiên — tại hạ tự hiểu ý đại hiệp\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💬 *VÍ DỤ CHAT TỰ NHIÊN* (không cần lệnh)\n"
        "• \"Kết quả U17 VN hôm qua thế nào?\" → tại hạ search Google\n"
        "• \"Ghi lại idea LiveOps Tết: tặng skin lì xì\" → tạo note\n"
        "• \"Nhắc tao 9h sáng mai họp QC\" → tạo lịch\n"
        "• \"Nhắc tao 30 phút trước cuộc họp QC\" → tạo reminder offset\n"
        "• \"Tóm tắt cho tao meeting này: [paste nội dung]\" → meeting minutes\n"
        "• \"Lưu data JX1 ARPU tháng 4: 45k VNĐ\" → save knowledge (product=JX1, game_data)\n"
        "• \"Phân tích retention JX2 của tao\" → search knowledge JX2 → phản biện\n"
        "• 📎 *Attach file (PDF/XLSX/TXT/CSV/MD/JSON)* + caption → tại hạ tự đọc, suy đoán product+category, tạo knowledge draft\n"
        "• 🖼️ *Gửi ảnh* (screenshot game / chart / design UI) + caption → Gemini Vision đọc → save knowledge\n"
        "• 🔗 *Paste URL* trong tin nhắn → tại hạ fetch nội dung, đọc và phản hồi (web article, blog, doc public)\n"
        "• \"Xuất report phân tích retention JX1 Q1\" → tạo file HTML đính kèm, mobile-friendly (work với mọi model, Claude Sonnet chất lượng best nếu có key)\n"
        "• \"Phân tích trade-off của subscription model cho game RPG\" → tư vấn\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📋 *LỆNH CHÍNH*\n"
        "• `/start` — đăng ký / về menu chính\n"
        "• `/help` — xem hướng dẫn này\n"
        "• `/schedules` — xem lịch sắp tới (có nút xoá)\n"
        "• `/notes` — xem note đã lưu (theo topic / theo ngày)\n"
        "• `/knowledge` — kho tri thức (data/design/behavior/market...)\n"
        "• `/status` — xem quota free tier còn lại\n\n"
        "🔑 *QUẢN LÝ API KEY & MODEL*\n"
        "• `/setkey` — nhập / đổi key Gemini / Groq / Claude\n"
        "• `/mykey` — xem trạng thái keys (đã có hay chưa)\n"
        "• `/removekey` — xoá toàn bộ keys\n"
        "• `/model` — chọn model AI (Auto = smart fallback, hoặc pin model cụ thể)\n"
        "• `/cancel` — huỷ flow đang chờ nhập input\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📱 *MENU GÓC DƯỚI* (bấm thay vì gõ lệnh)\n"
        "• 📅 Lịch  • 📝 Note  • 📚 Knowledge  • 🔑 Key  • 📊 Status\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⏰ *NHẮC NHỞ THÔNG MINH*\n"
        "• Reminder fire đúng giờ kèm 3 nút Snooze: ⏸ 10p / 30p / 1h\n"
        "• Có thể tạo reminder offset \"nhắc trước X phút\" so với lịch khác\n"
        "• 8:00 sáng mỗi ngày tại hạ tự gửi tóm tắt lịch hôm nay\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🛡️ *BẢO MẬT*\n"
        "• Keys mã hoá Fernet khi lưu DB\n"
        "• Tin nhắn chứa key tự xoá ngay sau khi save\n"
        "• Log không bao giờ chứa plaintext key\n"
        "• Chỉ chat riêng với bot, không paste key trong group\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💡 *MẸO*\n"
        "• Note có chủ đề (topic) — tại hạ sẽ gợi ý topic, đại hiệp pick hoặc nhập mới\n"
        "• Trước khi tạo note/lịch sẽ có nút ✅ duyệt / ❌ huỷ — review trước khi ghi\n"
        "• Hết quota free Gemini? đợi reset (RPM=1 phút, RPD=24h) hoặc upgrade trả phí\n"
        "• 9-tier fallback model (4 Gemini free + Groq + 2 Gemini Pro + 2 Claude) — `/model` để pin\n"
        "• Knowledge khác Note: knowledge cho data/design/research lâu dài, note cho idea/todo nhanh\n"
        "• Knowledge phân theo (product, category) — vd JX1/Game data, JX2/Design — tránh trộn data nhiều game"
    )
    if is_admin:
        base += (
            "\n\n━━━━━━━━━━━━━━━━━━\n"
            "👑 *LỆNH ADMIN*\n"
            "• `/pending` — danh sách user chờ duyệt\n"
            "• `/members` — quản lý user đã duyệt (xem stats / revoke / xoá)\n"
            "• `/listmodels` — list Gemini model API ID thực tế (debug)"
        )
    try:
        await update.message.reply_text(base, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(base)


async def setkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔑 Đại hiệp chọn loại key cần nhập:",
        reply_markup=setkey_keyboard(),
    )


async def mykey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        gemini, groq, claude = await keys_repo.get_decrypted_keys(session, user_id)

    def _mask(k: str | None) -> str:
        if not k:
            return "❌ chưa setup"
        return f"✅ `{k[:6]}...{k[-4:]}`"

    await update.message.reply_text(
        "🔑 *API keys của đại hiệp:*\n\n"
        f"• Gemini (bắt buộc): {_mask(gemini)}\n"
        f"• Groq (optional, free fallback): {_mask(groq)}\n"
        f"• Claude (optional, paid): {_mask(claude)}\n\n"
        "Thiếu key nào? Gõ /setkey để nhập.",
        parse_mode="Markdown",
    )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cho user pin model cụ thể, hoặc về 'auto' (smart 7-tier fallback)."""
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        current = await appr_repo.get_preferred_model(session, user_id)
    label = "🤖 Auto" if current == "auto" else f"📌 `{current}`"
    await update.message.reply_text(
        "🧠 *Chọn model AI:*\n\n"
        f"Hiện đang dùng: {label}\n\n"
        "• *Auto* — tại hạ tự chọn tier rẻ nhất phù hợp + fallback khi hết quota\n"
        "• *Pin model cụ thể* — luôn dùng model đó, KHÔNG fallback (báo lỗi nếu hết quota)\n"
        "• Paid models cần credit trên console tương ứng",
        parse_mode="Markdown",
        reply_markup=model_picker_keyboard(current),
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
    for k in (
        "awaiting_key", "awaiting_email", "awaiting_note_topic",
        "awaiting_knowledge_product", "awaiting_move_entry_product",
    ):
        context.user_data.pop(k, None)
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
        gemini_key, _, _ = await keys_repo.get_decrypted_keys(session, user_id)
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


async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        products = await knowledge_repo.list_products(session, user_id)
    if not products:
        await update.message.reply_text(
            "📚 Kho tri thức của đại hiệp đang trống.\n\n"
            "Cứ chat để lưu data/design/insight, vd:\n"
            "• \"Lưu data JX1 ARPU tháng 4: 45k VNĐ\" (auto product=JX1)\n"
            "• \"Thêm vào kho design guild JX2\"\n"
            "• \"Lưu market overview ngành mobile RPG\" (general, no product)"
        )
        return
    total = sum(c for _, c in products)
    await update.message.reply_text(
        f"📚 *Kho tri thức* — {total} entries / {len(products)} product\n\n"
        "Chọn product để xem:",
        parse_mode="Markdown",
        reply_markup=knowledge_root_keyboard(products),
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
