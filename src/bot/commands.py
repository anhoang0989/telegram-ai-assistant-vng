"""
Giữ lại 3 commands tối thiểu: /start (chào), /help (giải thích), /status (quota).
Mọi thứ khác → chat tự nhiên.
"""
from telegram import Update
from telegram.ext import ContextTypes
from src.ai.quota_tracker import quota_tracker


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Tao là trợ lý AI của mày.\n\n"
        "Cứ chat bình thường, tao tự hiểu ý mày:\n\n"
        "💬 *Hỏi đáp* — trend, số liệu, chiến lược, phản biện\n"
        "📅 *Đặt lịch* — vd: _\"nhắc tao 3h chiều mai họp product\"_\n"
        "📝 *Ghi chú* — vd: _\"ghi lại: KPI Q1 đạt 85%\"_\n"
        "🔍 *Tra cứu* — vd: _\"tao có note gì về KPI không?\"_\n"
        "📋 *Meeting* — paste nội dung + _\"tổng hợp giúp tao\"_\n\n"
        "Gõ /help để xem thêm, /status để xem quota AI.",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Cách dùng*\n\n"
        "Bot này hoạt động **100% qua chat tự nhiên** — không có menu hay command phức tạp.\n\n"
        "*Ví dụ:*\n"
        "• _\"trend mobile game VN 2026 như nào?\"_\n"
        "• _\"nhắc tao 9h sáng thứ 6 gửi report\"_\n"
        "• _\"ghi lại: review Q1 — DAU giảm 5%, churn tăng\"_\n"
        "• _\"tao có note gì về Q1?\"_\n"
        "• _\"lịch tuần này có gì?\"_\n"
        "• _\"tổng hợp meeting này: [paste nội dung]\"_\n\n"
        "*Lệnh tối thiểu:*\n"
        "• `/start` — chào\n"
        "• `/help` — hướng dẫn này\n"
        "• `/status` — xem quota AI các tier còn lại\n",
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = quota_tracker.status()
    tier_labels = {0: "T1 Flash Lite", 1: "T2 Flash", 2: "T3 Pro", 3: "T4 Groq"}
    lines = ["📊 *AI Quota Status:*\n"]
    for i, (model, s) in enumerate(status.items()):
        label = tier_labels.get(i, model)
        rpm_bar = "🟢" if s["rpm_used"] < s["rpm_limit"] * 0.8 else "🟡" if s["rpm_used"] < s["rpm_limit"] else "🔴"
        rpd_bar = "🟢" if s["rpd_used"] < s["rpd_limit"] * 0.8 else "🟡" if s["rpd_used"] < s["rpd_limit"] else "🔴"
        lines.append(
            f"{rpm_bar} *{label}*\n"
            f"  RPM: {s['rpm_used']}/{s['rpm_limit']} | RPD: {s['rpd_used']}/{s['rpd_limit']} {rpd_bar}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
