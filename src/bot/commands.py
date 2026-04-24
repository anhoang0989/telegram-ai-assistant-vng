"""
Commands:
  /start, /help — onboarding
  /setkey — lưu API keys (BYOK)
  /mykey — xem trạng thái keys
  /removekey — xoá keys
  /status — xem quota còn lại của user
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.db.session import AsyncSessionFactory
from src.db.repositories import user_keys as keys_repo
from src.ai.quota_tracker import quota_tracker

logger = logging.getLogger(__name__)


ONBOARDING_TEXT = (
    "👋 Chào! Tao là trợ lý AI cho dân vận hành game.\n\n"
    "*Bước 1 — Lấy API key miễn phí:*\n"
    "🔹 Gemini: https://aistudio.google.com/apikey\n"
    "🔹 Groq: https://console.groq.com/keys\n\n"
    "*Bước 2 — Setup key (nhắn riêng cho bot):*\n"
    "`/setkey gemini <GEMINI_KEY>`\n"
    "`/setkey groq <GROQ_KEY>`\n\n"
    "*Bước 3 — Chat bình thường:*\n"
    "💬 Hỏi đáp — trend, chiến lược, phản biện\n"
    "📅 Đặt lịch — _\"nhắc tao 3h chiều mai họp product\"_\n"
    "📝 Ghi chú — _\"ghi lại: KPI Q1 đạt 85%\"_\n"
    "🔍 Tra cứu — _\"tao có note gì về KPI không?\"_\n"
    "📋 Meeting — paste nội dung + _\"tổng hợp giúp tao\"_\n\n"
    "Gõ /help để xem đầy đủ lệnh."
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(ONBOARDING_TEXT, parse_mode="Markdown", disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Lệnh*\n\n"
        "• `/start` — hướng dẫn setup\n"
        "• `/setkey gemini <KEY>` — lưu Gemini key\n"
        "• `/setkey groq <KEY>` — lưu Groq key\n"
        "• `/mykey` — xem trạng thái keys\n"
        "• `/removekey` — xoá keys\n"
        "• `/status` — xem quota còn lại\n\n"
        "Ngoài ra cứ chat tự nhiên, bot tự hiểu ý.\n\n"
        "⚠️ *Bảo mật:* keys được mã hoá Fernet trước khi lưu DB. "
        "Nên nhắn `/setkey` trong chat riêng với bot, không share nhóm.",
        parse_mode="Markdown",
    )


async def setkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    args = context.args or []

    if len(args) < 2:
        await update.message.reply_text(
            "Cú pháp: `/setkey gemini <KEY>` hoặc `/setkey groq <KEY>`",
            parse_mode="Markdown",
        )
        return

    provider = args[0].lower()
    key = args[1].strip()

    if provider not in ("gemini", "groq"):
        await update.message.reply_text("Provider phải là `gemini` hoặc `groq`.", parse_mode="Markdown")
        return

    if len(key) < 10:
        await update.message.reply_text("Key trông không hợp lệ (quá ngắn).")
        return

    async with AsyncSessionFactory() as session:
        if provider == "gemini":
            await keys_repo.set_keys(session, user_id, gemini_key=key)
        else:
            await keys_repo.set_keys(session, user_id, groq_key=key)

    # Delete the user's message to hide the key from chat history
    try:
        await update.message.delete()
    except Exception:
        pass

    await update.effective_chat.send_message(
        f"✅ Đã lưu {provider.capitalize()} key (đã mã hoá). Tin nhắn chứa key đã xoá.\n\n"
        "Dùng /mykey để kiểm tra."
    )


async def mykey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        gemini, groq = await keys_repo.get_decrypted_keys(session, user_id)

    def _mask(k: str | None) -> str:
        if not k:
            return "❌ chưa setup"
        return f"✅ {k[:6]}...{k[-4:]}"

    await update.message.reply_text(
        f"🔑 *API keys của bạn:*\n\n"
        f"• Gemini: {_mask(gemini)}\n"
        f"• Groq: {_mask(groq)}",
        parse_mode="Markdown",
    )


async def removekey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with AsyncSessionFactory() as session:
        removed = await keys_repo.remove(session, user_id)
    if removed:
        await update.message.reply_text("🗑️ Đã xoá toàn bộ keys. Muốn dùng lại thì `/setkey`.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Bạn chưa có key nào để xoá.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    status = quota_tracker.status(user_id)
    tier_labels = {0: "T1 Flash Lite", 1: "T2 Flash", 2: "T3 Pro", 3: "T4 Groq"}
    lines = ["📊 *Quota của bạn hôm nay:*\n"]
    for i, (model, s) in enumerate(status.items()):
        label = tier_labels.get(i, model)
        rpm_bar = "🟢" if s["rpm_used"] < s["rpm_limit"] * 0.8 else "🟡" if s["rpm_used"] < s["rpm_limit"] else "🔴"
        rpd_bar = "🟢" if s["rpd_used"] < s["rpd_limit"] * 0.8 else "🟡" if s["rpd_used"] < s["rpd_limit"] else "🔴"
        lines.append(
            f"{rpm_bar} *{label}*\n"
            f"  RPM: {s['rpm_used']}/{s['rpm_limit']} | RPD: {s['rpd_used']}/{s['rpd_limit']} {rpd_bar}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
