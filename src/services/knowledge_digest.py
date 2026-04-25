"""
Weekly knowledge digest — Chủ nhật 9h sáng.
Cho mỗi user approved có entries trong 7 ngày qua, gọi Gemini gen 1 tóm tắt
dạng: 3 câu hỏi mở + 2 cảnh báo + 1 gợi ý vận hành.
"""
import logging
from google import genai
from google.genai import types as gtypes
from src.db.models import KnowledgeEntry

logger = logging.getLogger(__name__)

DIGEST_MODEL = "gemini-2.5-flash"  # đủ tốt cho digest text-only, ít tốn quota

DIGEST_PROMPT = """Tại hạ là trợ lý AI cá nhân của đại hiệp — chuyên gia game industry.

Đại hiệp vừa nhập {count} entries vào kho tri thức trong 7 ngày qua. Liệt kê dưới đây.

NHIỆM VỤ: Đọc kỹ và viết 1 weekly digest gồm 4 phần:

📊 **Tóm tắt** (1-2 câu): những gì đại hiệp đã ghi nhận tuần qua
❓ **3 câu hỏi mở** đáng suy nghĩ — dựa trên data thực tế của đại hiệp, KHÔNG bịa
⚠️ **2 cảnh báo / điểm rủi ro** — phát hiện mâu thuẫn, gap, hoặc rủi ro vận hành nếu có. Nếu không có rủi ro rõ → nói "tuần này tại hạ chưa thấy red flag"
💡 **1 gợi ý vận hành** cho tuần tới — actionable, cụ thể, dựa trên data chứ không chung chung

Tone: tại hạ / đại hiệp, sắc sảo, đi thẳng vấn đề, không nịnh.
Format: Markdown, tổng độ dài 250-400 từ.

────── ENTRIES ──────
{entries_text}
"""


def _format_entry(e: KnowledgeEntry) -> str:
    prod = e.product or "General"
    body = e.content[:500]
    if len(e.content) > 500:
        body += "…"
    tags = (" [" + ", ".join(e.tags) + "]") if e.tags else ""
    return (
        f"[{prod} | {e.category}] {e.title}{tags}\n"
        f"  {body}\n"
    )


async def generate_digest(api_key: str, entries: list[KnowledgeEntry]) -> str | None:
    """Gen digest qua Gemini direct call. Trả None nếu fail."""
    if not entries:
        return None
    entries_text = "\n".join(_format_entry(e) for e in entries[:30])
    prompt = DIGEST_PROMPT.format(count=len(entries), entries_text=entries_text)

    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=DIGEST_MODEL,
            contents=prompt,
            config=gtypes.GenerateContentConfig(temperature=0.7),
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.warning(f"generate_digest failed: {e}")
        return None
