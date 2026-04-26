"""
Mô tả ảnh upload qua Gemini Vision — dùng gemini-2.5-flash (cheap + tốt cho image).
Output là text mô tả CHI TIẾT để LLM tiếp theo có thể save_knowledge.
"""
import logging
from google import genai
from google.genai import types as gtypes

logger = logging.getLogger(__name__)

VISION_MODEL = "gemini-2.5-flash"
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB

DESCRIBE_PROMPT = """Mô tả CHI TIẾT ảnh này theo định dạng có cấu trúc, ưu tiên thông tin có thể lưu làm knowledge:

1. **Loại nội dung**: screenshot game / biểu đồ / design UI / spreadsheet / chart data / sketch / khác
2. **Tóm tắt 1 dòng**: nội dung chính
3. **Số liệu / data** (nếu có): liệt kê EXACT số liệu, tỷ lệ %, KPI nhìn thấy
4. **Text trong ảnh**: trích xuất chữ/label/UI text quan trọng (OCR-style)
5. **Insight chính**: pattern / so sánh / cảnh báo nếu phát hiện được

Trả lời tiếng Việt, ngắn gọn nhưng đầy đủ, KHÔNG lan man."""


async def describe_image(
    api_key: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    user_hint: str = "",
) -> str:
    """Gọi Gemini Vision mô tả ảnh. Raise nếu fail."""
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"Ảnh quá lớn ({len(image_bytes)/1024/1024:.1f}MB > 10MB)")

    prompt = DESCRIBE_PROMPT
    if user_hint.strip():
        prompt += f"\n\n**Caption từ user**: {user_hint.strip()}"

    client = genai.Client(api_key=api_key)
    image_part = gtypes.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response = await client.aio.models.generate_content(
        model=VISION_MODEL,
        contents=[image_part, prompt],
        config=gtypes.GenerateContentConfig(temperature=0.3),
    )
    return (response.text or "").strip()
