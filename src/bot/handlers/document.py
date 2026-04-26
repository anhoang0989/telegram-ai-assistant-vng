"""
Document + Photo upload handler — user gửi file/ảnh → bot extract content →
AI auto-categorize → tạo knowledge draft → user confirm flow.

Flow:
  - Document: extract text via file_extractor → synthesize → run_llm_turn
  - Photo: describe via Gemini Vision → synthesize → run_llm_turn
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.services import file_extractor
from src.services import image_describe
from src.db.session import AsyncSessionFactory
from src.db.repositories import user_keys as keys_repo
from src.bot.handlers.chat import run_llm_turn

logger = logging.getLogger(__name__)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if msg is None or msg.document is None:
        return
    doc = msg.document
    filename = doc.file_name or "uploaded"
    size = doc.file_size or 0

    if size > file_extractor.MAX_FILE_BYTES:
        await msg.reply_text(
            f"⚠️ File quá lớn ({size/1024/1024:.1f}MB). Tối đa 10MB."
        )
        return

    if not file_extractor.is_supported(filename):
        from pathlib import Path
        ext = Path(filename).suffix
        await msg.reply_text(
            f"⚠️ Không hỗ trợ định dạng `{ext}`.\n"
            f"Hỗ trợ: txt, md, csv, tsv, pdf, xlsx, log, json.",
            parse_mode="Markdown",
        )
        return

    # Download bytes
    try:
        await msg.chat.send_action("upload_document")
        tg_file = await context.bot.get_file(doc.file_id)
        # Telegram bot API: Bytearray via download_as_bytearray
        file_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        logger.error(f"Download failed: {e}")
        await msg.reply_text(f"⚠️ Tải file lỗi: {e}")
        return

    # Extract text
    try:
        text, summary = file_extractor.extract_text(filename, file_bytes)
    except ValueError as e:
        await msg.reply_text(f"⚠️ {e}")
        return
    except Exception as e:
        logger.error(f"Extract failed for {filename}: {e}", exc_info=True)
        await msg.reply_text(f"⚠️ Không trích xuất được text: {e}")
        return

    if not text.strip():
        await msg.reply_text("⚠️ File trống hoặc không có text trích xuất được.")
        return

    user_caption = (msg.caption or "").strip()
    caption_hint = f"\n\nGhi chú từ đại hiệp: {user_caption}" if user_caption else ""

    # Synthesize message để LLM tự động save_knowledge với product/category infer được
    llm_text = (
        f"[ĐẠI HIỆP UPLOAD FILE: `{filename}` ({summary})]{caption_hint}\n\n"
        f"--- Nội dung file ---\n{text}\n--- Hết ---\n\n"
        "Hãy lưu nội dung này vào kho tri thức (gọi `save_knowledge`). "
        "Tự suy đoán:\n"
        "- `product`: nếu file/caption mention game cụ thể (vd: JX1, JX2). Nếu data chung → bỏ qua product.\n"
        "- `category`: 1 trong game_data | design | user_behavior | market | meeting_log | other.\n"
        "- `title`: ngắn gọn dựa trên nội dung file (KHÔNG dùng tên file).\n"
        "- `content`: tóm tắt CÔ ĐỌNG nội dung file (giữ số liệu/insight quan trọng, bỏ noise).\n"
        "- `tags`: 2-4 tags ngắn nếu có thể."
    )

    # Conv history giữ ngắn (không lưu full content)
    conv_text = f"[Đã upload file: {filename} — {summary}]"
    if user_caption:
        conv_text += f" — caption: {user_caption}"

    await run_llm_turn(update, context, llm_text=llm_text, conv_user_text=conv_text)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User gửi ảnh → Gemini Vision mô tả → save_knowledge auto."""
    msg = update.message
    if msg is None or not msg.photo:
        return
    user_id = update.effective_user.id

    # Lấy size lớn nhất (last = highest resolution)
    photo = msg.photo[-1]
    user_caption = (msg.caption or "").strip()

    # Cần Gemini key để gọi Vision
    async with AsyncSessionFactory() as session:
        gemini_key, _, _ = await keys_repo.get_decrypted_keys(session, user_id)
    if not gemini_key:
        await msg.reply_text(
            "🔒 Cần Gemini key để đọc ảnh. Gõ /setkey nhập trước nhé."
        )
        return

    try:
        await msg.chat.send_action("upload_photo")
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception as e:
        logger.error(f"Photo download failed: {e}")
        await msg.reply_text(f"⚠️ Tải ảnh lỗi: {e}")
        return

    if len(img_bytes) > image_describe.MAX_IMAGE_BYTES:
        await msg.reply_text(
            f"⚠️ Ảnh quá lớn ({len(img_bytes)/1024/1024:.1f}MB > 10MB)."
        )
        return

    # Mô tả ảnh qua Gemini Vision
    try:
        await msg.chat.send_action("typing")
        description = await image_describe.describe_image(
            api_key=gemini_key,
            image_bytes=img_bytes,
            mime_type="image/jpeg",  # Telegram photo luôn JPEG
            user_hint=user_caption,
        )
    except Exception as e:
        logger.error(f"describe_image failed: {e}", exc_info=True)
        await msg.reply_text(f"⚠️ Đọc ảnh lỗi: {e}")
        return

    if not description.strip():
        await msg.reply_text("⚠️ Không đọc được nội dung ảnh.")
        return

    caption_hint = f"\n\nCaption từ đại hiệp: {user_caption}" if user_caption else ""
    llm_text = (
        f"[ĐẠI HIỆP UPLOAD ẢNH] (Gemini Vision đã đọc nội dung){caption_hint}\n\n"
        f"--- Nội dung ảnh ---\n{description}\n--- Hết ---\n\n"
        "Hãy lưu nội dung này vào kho tri thức (gọi `save_knowledge`). "
        "Tự suy đoán product (nếu mention game), category, title, content súc tích, tags."
    )
    conv_text = "[Đã upload ảnh]"
    if user_caption:
        conv_text += f" — caption: {user_caption}"

    await run_llm_turn(update, context, llm_text=llm_text, conv_user_text=conv_text)
