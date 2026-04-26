"""
Text handler — paths:
  1. awaiting_email          → đăng ký
  2. awaiting_key            → nhập API key
  3. awaiting_note_topic     → nhập tên topic mới cho note draft
  4. persistent menu shortcuts (📅 Lịch, 📝 Note, 🔑 Key, 📊 Status)
  5. default                 → chat LLM. Nếu LLM tạo draft → show pick-topic / confirm keyboard.
"""
import asyncio
import logging
import re
from telegram import Update
from telegram.ext import ContextTypes
from src.config import settings
from src.db.session import AsyncSessionFactory
from src.db.repositories import conversation as conv_repo
from src.db.repositories import user_keys as keys_repo
from src.db.repositories import approvals as appr_repo
from src.db.repositories import notes as notes_repo
from src.db.repositories import schedules as sched_repo
from src.ai.llm_router import chat
from src.bot import drafts
from src.bot.keyboards import (
    approval_keyboard,
    setkey_keyboard,
    persistent_menu,
    note_topic_picker,
    note_confirm_keyboard,
    schedule_confirm_keyboard,
    schedules_list_keyboard,
    notes_root_keyboard,
    knowledge_confirm_keyboard,
    CATEGORY_LABELS,
    PAGE_SIZE,
)

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MSG = 4000
DOMAIN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,19}$")
TYPING_REFRESH_SEC = 4.0  # Telegram giữ "typing..." ~5s, refresh mỗi 4s


async def _typing_loop(chat, stop_event: asyncio.Event) -> None:
    """Gửi send_action('typing') liên tục đến khi stop_event được set.
    Để user biết bot đang xử lý, không tưởng bot chết."""
    while not stop_event.is_set():
        try:
            await chat.send_action("typing")
        except Exception:
            pass  # network blip, ignore — sẽ retry vòng sau
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TYPING_REFRESH_SEC)
        except asyncio.TimeoutError:
            continue

# Persistent menu shortcuts → command-like behavior
MENU_SHORTCUTS = {"📅 Lịch", "📝 Note", "📚 Knowledge", "🔑 Key", "📊 Status", "👑 Members"}


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    text = update.message.text or ""

    # Flow 1: signup
    if context.user_data.get("awaiting_email"):
        await _handle_signup(update, context, text)
        return

    # Flow 2: key input
    if context.user_data.get("awaiting_key"):
        await _handle_key_input(update, context, text)
        return

    # Flow 3: awaiting new topic name for note draft
    if context.user_data.get("awaiting_note_topic"):
        await _handle_new_topic_input(update, context, text)
        return

    # Flow 3b: awaiting new product name for knowledge draft
    if context.user_data.get("awaiting_knowledge_product"):
        await _handle_new_knowledge_product_input(update, context, text)
        return

    # Flow 3c: awaiting move entry to new product
    if context.user_data.get("awaiting_move_entry_product"):
        await _handle_move_entry_product_input(update, context, text)
        return

    # Flow 4: persistent menu shortcuts
    if text.strip() in MENU_SHORTCUTS:
        await _handle_menu_shortcut(update, context, text.strip())
        return

    # Flow 5: normal chat — phát hiện URL → fetch + augment trước
    from src.services import url_fetcher
    urls = url_fetcher.extract_urls(text, limit=2)
    llm_text = text
    conv_text = text
    if urls:
        await update.message.chat.send_action("typing")
        fetched_blocks = []
        ok_count = 0
        for u in urls:
            try:
                page_text, page_title = await url_fetcher.fetch_url(u)
                fetched_blocks.append(
                    f"--- URL: {u}\nTitle: {page_title}\n---\n{page_text}\n--- Hết URL ---"
                )
                ok_count += 1
            except Exception as e:
                logger.warning(f"URL fetch failed {u}: {e}")
                await update.message.reply_text(f"⚠️ Không đọc được {u[:60]}: {e}")
        if fetched_blocks:
            joined = "\n\n".join(fetched_blocks)
            llm_text = f"{text}\n\n[NỘI DUNG TỪ URL ĐẠI HIỆP CHIA SẺ]\n\n{joined}"
            conv_text = text + f" [+{ok_count} URL fetched]"

    await run_llm_turn(update, context, llm_text=llm_text, conv_user_text=conv_text)


async def run_llm_turn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    llm_text: str,
    conv_user_text: str | None = None,
) -> None:
    """Core LLM turn: gọi chat() với typing loop, render draft hoặc response.
    Dùng chung cho text chat và document upload (synthesized message).

    llm_text: text gửi cho LLM (có thể chứa file content lớn)
    conv_user_text: text lưu vào conversation history (giữ ngắn cho doc upload).
                    Nếu None → dùng llm_text.
    """
    user_id = update.effective_user.id
    save_text = conv_user_text if conv_user_text is not None else llm_text

    async with AsyncSessionFactory() as session:
        gemini_key, groq_key, claude_key = await keys_repo.get_decrypted_keys(session, user_id)

        if not gemini_key:
            await update.message.reply_text(
                "🔒 Đại hiệp chưa có Gemini key (bắt buộc — workhorse free tier).\n"
                "Gõ /setkey để nhập. Groq + Claude là optional fallback."
            )
            return

        history_records = await conv_repo.get_recent(session, user_id)
        history = [{"role": r.role, "content": r.content} for r in history_records]
        preferred = await appr_repo.get_preferred_model(session, user_id)

        await conv_repo.save(session, user_id, "user", save_text)

        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(_typing_loop(update.message.chat, stop_typing))

        try:
            response_text, model_used = await chat(
                session, user_id, history, llm_text,
                gemini_key=gemini_key, groq_key=groq_key, claude_key=claude_key,
                preferred_model=preferred,
            )
        except Exception as e:
            logger.error(f"chat() error: {e}", exc_info=True)
            response_text = f"⚠️ Tại hạ gặp lỗi khi xử lý: {e}"
            model_used = "error"
        finally:
            stop_typing.set()
            try:
                await asyncio.wait_for(typing_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                typing_task.cancel()

        logger.info(f"[{user_id}] Served by: {model_used}")
        await conv_repo.save(session, user_id, "assistant", response_text)

        note_draft = drafts.get_note_draft(user_id)
        sched_draft = drafts.get_schedule_draft(user_id)
        know_draft = drafts.get_knowledge_draft(user_id)
        pending_report = drafts.get_report(user_id)

        # Defensive: detect AI hallucinated save without actually calling save tool.
        # Phrases observed in production faking save:
        _fake_save_phrases = (
            "đã lưu thông tin", "đã lưu data", "đã lưu vào kho",
            "đã save", "đã ghi vào kho", "đã thêm vào kho",
            "đã được ghi nhận", "đã được lưu", "lưu trực tiếp vào hệ thống",
            "lưu thẳng vào hệ thống", "lưu vào hệ thống để đại hiệp",
            "dữ liệu đã được", "đã được tại hạ ghi",
        )
        # Pattern fake: AI tự format bullet list giả vờ là tool result
        # "**Sản phẩm:** X / **Danh mục:** Y / **Tiêu đề:** ..."
        rt = response_text or ""
        rt_lower = rt.lower()
        has_fake_phrase = any(p in rt_lower for p in _fake_save_phrases)
        has_tool_result_format = (
            ("**sản phẩm:**" in rt_lower or "**product:**" in rt_lower)
            and ("**danh mục:**" in rt_lower or "**category:**" in rt_lower)
        )
        if (has_fake_phrase or has_tool_result_format) and not (know_draft or note_draft):
            logger.warning(
                f"[{user_id}] HALLUCINATION detected (phrase={has_fake_phrase} "
                f"toolFormat={has_tool_result_format}). "
                f"Response head: {rt[:300]!r}"
            )
            response_text = (
                "⚠️ Tại hạ vừa định trả lời sai (giả vờ đã lưu mà thực ra chưa gọi tool). "
                "Đại hiệp gõ lại yêu cầu rõ — vd: '**lưu lại data này vào knowledge**' — "
                "tại hạ sẽ tạo draft đúng kèm nút duyệt ✅/❌.\n\n"
                "(Response gốc đã invalidate, không tin được):\n\n" + rt[:1500]
            )

        if note_draft:
            await _send_note_topic_picker(update, session, user_id, note_draft, response_text)
            return
        if sched_draft:
            await _send_schedule_confirm(update, sched_draft, response_text)
            return
        if know_draft:
            await _send_knowledge_confirm(update, know_draft, response_text)
            return
        if pending_report:
            await _send_html_report(update, response_text)
            return

    await _send_long(update, response_text)


async def _send_html_report(update: Update, llm_text: str) -> None:
    """Pop pending HTML report → gửi file kèm caption."""
    import io
    user_id = update.effective_user.id
    report = drafts.pop_report(user_id)
    if not report:
        return
    bio = io.BytesIO(report["html"].encode("utf-8"))
    bio.name = report["filename"]
    summary = report.get("summary") or ""
    caption_lines = [f"📄 {report['filename']}"]
    if summary:
        caption_lines.append(summary[:400])
    if llm_text and llm_text.strip():
        caption_lines.append(llm_text.strip()[:400])
    caption = "\n\n".join(caption_lines)[:1024]  # Telegram caption max 1024
    try:
        await update.message.reply_document(
            document=bio,
            filename=report["filename"],
            caption=caption,
        )
    except Exception as e:
        logger.error(f"send report file failed: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ Tạo report xong nhưng gửi file lỗi: {e}\n{llm_text[:500]}"
        )


async def _send_long(update: Update, text: str) -> None:
    for i in range(0, len(text), MAX_TELEGRAM_MSG):
        chunk = text[i:i + MAX_TELEGRAM_MSG]
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(chunk)


async def _send_note_topic_picker(update, session, user_id, draft, llm_text):
    """Tách ack + preview+buttons thành 2 message để buttons luôn render."""
    if llm_text and llm_text.strip():
        try:
            await update.message.reply_text(llm_text[:MAX_TELEGRAM_MSG], parse_mode="Markdown")
        except Exception:
            try:
                await update.message.reply_text(llm_text[:MAX_TELEGRAM_MSG])
            except Exception:
                pass

    topics = await notes_repo.list_topics(session, user_id)
    existing = [t for (t, _) in topics]
    preview = (
        f"📝 Note draft\n{draft['title']}\n\n{draft['content']}\n\n"
        "Đại hiệp chọn topic:"
    )
    preview = preview[:MAX_TELEGRAM_MSG]
    kb = note_topic_picker(draft["draft_id"], existing, draft.get("suggested_topic"))
    try:
        await update.message.reply_text(preview, reply_markup=kb)
        logger.info(f"[{user_id}] note picker sent, draft_id={draft['draft_id']}")
    except Exception as e:
        logger.error(f"[{user_id}] note picker fail: {e}")


async def _send_knowledge_confirm(update, draft, llm_text):
    """Gửi ack text + preview+buttons thành 2 message TÁCH RIÊNG.
    Trước đây gộp 1 message → nếu llm_text có Markdown lỗi → fallback plain
    text → truncate sai → buttons có thể không render. Tách 2 → tin cậy hơn.
    """
    user_id = update.effective_user.id

    # Message 1: LLM ack (optional, có thể fail riêng không ảnh hưởng preview)
    if llm_text and llm_text.strip():
        try:
            await update.message.reply_text(llm_text[:MAX_TELEGRAM_MSG], parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"[{user_id}] ack markdown fail: {e}, retry plain")
            try:
                await update.message.reply_text(llm_text[:MAX_TELEGRAM_MSG])
            except Exception as e2:
                logger.error(f"[{user_id}] ack plain also fail: {e2}")

    # Message 2: Preview + buttons (CRITICAL — phải render được)
    cat_label = CATEGORY_LABELS.get(draft["category"], draft["category"])
    prod_label = f"🎮 {draft['product']}" if draft.get("product") else "🌐 General"
    tags_line = (" 🏷️ " + ", ".join(draft["tags"])) if draft.get("tags") else ""
    body = draft["content"]
    if len(body) > 600:
        body = body[:600] + "…(truncated)"

    related = draft.get("related") or []
    related_section = ""
    if related:
        related_lines = [f"\n\n📎 Có {len(related)} entry liên quan cùng scope — review để tránh duplicate:"]
        for r in related[:5]:
            related_lines.append(f"  • {r['title'][:80]}")
        related_section = "\n".join(related_lines)

    preview = (
        f"📚 Knowledge draft\n"
        f"{prod_label} | {cat_label}\n"
        f"📝 {draft['title']}{tags_line}\n\n"
        f"{body}"
        f"{related_section}\n\n"
        f"Duyệt? (sai product → ✏️ Đổi product)"
    )
    preview = preview[:MAX_TELEGRAM_MSG]
    kb = knowledge_confirm_keyboard(draft["draft_id"])
    try:
        await update.message.reply_text(preview, reply_markup=kb)
        logger.info(f"[{user_id}] knowledge preview sent, draft_id={draft['draft_id']}")
    except Exception as e:
        logger.error(f"[{user_id}] preview send FAILED: {e}", exc_info=True)
        # Last resort: plain text + simple inline button
        try:
            await update.message.reply_text(
                f"⚠️ Preview render lỗi nhưng draft đã chuẩn bị.\n"
                f"Product: {draft.get('product') or 'General'} | Category: {draft['category']}\n"
                f"Title: {draft['title'][:100]}\n\nBấm để confirm:",
                reply_markup=kb,
            )
        except Exception as e2:
            logger.error(f"[{user_id}] last-resort send fail: {e2}")


async def _handle_move_entry_product_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
) -> None:
    """User vừa nhập product mới sau khi bấm 📂 Đổi product trong entry detail."""
    from src.db.repositories import knowledge as knowledge_repo
    user_id = update.effective_user.id
    entry_id = context.user_data.pop("awaiting_move_entry_product", None)
    if entry_id is None:
        return
    raw = text.strip()
    if raw.lower() in ("_general_", "none", "general", "_g_"):
        new_product = None
    else:
        new_product = knowledge_repo.normalize_product(raw)
    async with AsyncSessionFactory() as session:
        ok = await knowledge_repo.update_product(session, user_id, entry_id, new_product)
        if not ok:
            await update.message.reply_text("❌ Không update được entry.")
            return
        entry = await knowledge_repo.get(session, user_id, entry_id)
    label = f"🎮 {entry.product}" if entry.product else "🌐 General"
    await update.message.reply_text(
        f"✅ Đã chuyển entry *{entry.title}* sang {label}.\n"
        "Gõ /knowledge để xem lại.",
        parse_mode="Markdown",
    )


async def _handle_new_knowledge_product_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
) -> None:
    """User vừa nhập product name mới sau khi bấm ✏️ Đổi product."""
    from src.db.repositories import knowledge as knowledge_repo
    user_id = update.effective_user.id
    draft_id = context.user_data.pop("awaiting_knowledge_product", None)
    raw = text.strip()
    if raw.lower() in ("_general_", "none", "general", "_g_"):
        new_product = None  # explicit general
    else:
        new_product = knowledge_repo.normalize_product(raw)
    draft = drafts.update_knowledge_product(user_id, new_product)
    if not draft or draft["draft_id"] != draft_id:
        await update.message.reply_text("⚠️ Draft đã hết hạn.")
        return
    # Re-render preview
    await _send_knowledge_confirm(update, draft, "")


async def _send_schedule_confirm(update, draft, llm_text):
    """Tách ack + preview+buttons thành 2 message để buttons luôn render."""
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    user_id = update.effective_user.id

    if llm_text and llm_text.strip():
        try:
            await update.message.reply_text(llm_text[:MAX_TELEGRAM_MSG], parse_mode="Markdown")
        except Exception:
            try:
                await update.message.reply_text(llm_text[:MAX_TELEGRAM_MSG])
            except Exception:
                pass

    tz = ZoneInfo(settings.scheduler_timezone)
    try:
        dt = _dt.fromisoformat(draft["scheduled_at"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        time_str = dt.astimezone(tz).strftime("%d/%m/%Y %H:%M")
    except Exception:
        time_str = draft["scheduled_at"]
    preview = (
        f"📌 Lịch draft\n{draft['title']}\n🕐 {time_str}\n"
        f"🔁 {draft['recurrence']}"
    )
    if draft.get("description"):
        preview += f"\n{draft['description']}"
    preview = preview[:MAX_TELEGRAM_MSG]
    kb = schedule_confirm_keyboard(draft["draft_id"])
    try:
        await update.message.reply_text(preview, reply_markup=kb)
        logger.info(f"[{user_id}] schedule preview sent, draft_id={draft['draft_id']}")
    except Exception as e:
        logger.error(f"[{user_id}] schedule preview fail: {e}")


async def _handle_new_topic_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    user_id = update.effective_user.id
    draft_id = context.user_data.pop("awaiting_note_topic", None)
    topic = text.strip()[:200]
    if len(topic) < 1:
        await update.message.reply_text("⚠️ Topic không được để trống.")
        return
    draft = drafts.update_note_topic(user_id, topic)
    if not draft or draft["draft_id"] != draft_id:
        await update.message.reply_text("⚠️ Draft đã hết hạn.")
        return
    await update.message.reply_text(
        f"📁 Topic: *{topic}*\n📝 *{draft['title']}*\n\n{draft['content']}\n\nDuyệt?",
        parse_mode="Markdown",
        reply_markup=note_confirm_keyboard(draft_id),
    )


async def _handle_menu_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Map persistent reply-keyboard buttons → corresponding command flow."""
    user_id = update.effective_user.id
    if text == "📅 Lịch":
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
    elif text == "📝 Note":
        await update.message.reply_text(
            "📝 *Note của đại hiệp*\n\nXem theo:",
            parse_mode="Markdown",
            reply_markup=notes_root_keyboard(),
        )
    elif text == "📚 Knowledge":
        from src.bot.commands import knowledge_command
        await knowledge_command(update, context)
    elif text == "🔑 Key":
        await update.message.reply_text(
            "🔑 Đại hiệp chọn loại key cần nhập:",
            reply_markup=setkey_keyboard(),
        )
    elif text == "📊 Status":
        from src.bot.commands import status_command
        await status_command(update, context)
    elif text == "👑 Members":
        from src.bot.commands import members_command
        await members_command(update, context)


async def _handle_signup(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    user = update.effective_user
    text = text.strip()

    if not DOMAIN_RE.match(text):
        await update.message.reply_text(
            "⚠️ Domain không hợp lệ. Chỉ gồm chữ/số, 2-20 ký tự. Thử lại (vd: `AnH`, `TuVH`):",
            parse_mode="Markdown",
        )
        return

    async with AsyncSessionFactory() as session:
        row = await appr_repo.create_pending(
            session,
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            email_or_domain=text,
        )

    context.user_data.pop("awaiting_email", None)

    await update.message.reply_text(
        "✅ Tại hạ đã nhận yêu cầu của đại hiệp.\n"
        f"🆔 Domain: `{text}`\n\n"
        "⏳ Vui lòng chờ admin duyệt. Tại hạ sẽ báo lại khi có kết quả.",
        parse_mode="Markdown",
    )

    try:
        uname = f"@{user.username}" if user.username else "(no username)"
        admin_text = (
            "🆕 *Yêu cầu đăng ký mới*\n\n"
            f"👤 *{user.full_name or 'Không rõ tên'}* {uname}\n"
            f"🆔 Telegram ID: `{user.id}`\n"
            f"🏷️ Domain: `{text}`"
        )
        await context.bot.send_message(
            chat_id=settings.admin_user_id,
            text=admin_text,
            parse_mode="Markdown",
            reply_markup=approval_keyboard(user.id),
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")


async def _handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    user_id = update.effective_user.id
    provider = context.user_data.pop("awaiting_key", None)
    key = text.strip()

    if len(key) < 10 or " " in key or "\n" in key:
        await update.message.reply_text("⚠️ Key trông không hợp lệ. Gõ /setkey để thử lại.")
        return

    async with AsyncSessionFactory() as session:
        if provider == "gemini":
            await keys_repo.set_keys(session, user_id, gemini_key=key)
        elif provider == "groq":
            await keys_repo.set_keys(session, user_id, groq_key=key)
        elif provider == "claude":
            await keys_repo.set_keys(session, user_id, claude_key=key)
        else:
            await update.message.reply_text("⚠️ Provider không hợp lệ.")
            return

    try:
        await update.message.delete()
    except Exception:
        pass

    label = {"gemini": "Gemini", "groq": "Groq", "claude": "Claude"}.get(provider, provider)
    await update.effective_chat.send_message(
        f"✅ Tại hạ đã lưu {label} key (đã mã hoá). Tin nhắn chứa key đã xoá.\n\n"
        "Gõ /mykey để kiểm tra, /setkey để nhập thêm key khác.",
        reply_markup=persistent_menu(is_admin=(user_id == settings.admin_user_id)),
    )
