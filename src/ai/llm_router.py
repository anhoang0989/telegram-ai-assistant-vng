"""
LLM Router + Agentic Loop (BYOK edition).

Flow:
  1. Build messages từ DB history + tin nhắn mới
  2. Gọi LLM (tier thấp nhất phù hợp với complexity)
  3. Nếu LLM trả tool_calls → execute → feed kết quả ngược lại → gọi LLM lại
  4. Lặp đến khi LLM không gọi tool nữa, trả về text cuối cùng cho user

Quota + keys phân theo user_id → mỗi người free tier riêng.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.ai.classifier import classify, COMPLEXITY_START
from src.ai.quota_tracker import quota_tracker
from src.ai.providers import call_gemini, call_groq
from src.ai.tools import TOOLS
from src.bot.tool_dispatcher import dispatch_tool

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 8000
MAX_HISTORY_TURNS = 20
MAX_AGENTIC_STEPS = 5

TIERS = [
    {"model": settings.llm_tier1, "provider": "gemini"},  # 3-flash-lite — workhorse
    {"model": settings.llm_tier2, "provider": "gemini"},  # 2.5-flash-lite — backup
    {"model": settings.llm_tier3, "provider": "gemini"},  # 3-flash — reasoning
    {"model": settings.llm_tier4, "provider": "gemini"},  # 2.5-flash — backup reasoning
    {"model": settings.llm_tier5, "provider": "groq"},    # llama — cross-provider backup
    {"model": settings.llm_tier6, "provider": "gemini"},  # 3-pro — paid only
    {"model": settings.llm_tier7, "provider": "gemini"},  # 2.5-pro — paid only
]


async def _call_tier(
    tier: dict,
    messages: list[dict],
    gemini_key: str,
    groq_key: str,
) -> tuple[str, list[dict] | None]:
    if tier["provider"] == "gemini":
        return await call_gemini(gemini_key, tier["model"], messages, TOOLS)
    return await call_groq(groq_key, tier["model"], messages, TOOLS)


async def _call_with_fallback(
    user_id: int,
    messages: list[dict],
    start_tier: int,
    gemini_key: str,
    groq_key: str,
) -> tuple[str, list[dict] | None, str]:
    for i in range(start_tier, len(TIERS)):
        tier = TIERS[i]
        model = tier["model"]

        if not quota_tracker.available(user_id, model):
            logger.info(f"[{user_id}] Tier {i} ({model}) quota exhausted (local), falling back")
            continue

        try:
            text, tool_calls = await _call_tier(tier, messages, gemini_key, groq_key)
            # Record AFTER success — call fail không nên tốn quota counter local
            quota_tracker.record(user_id, model)
            return text, tool_calls, model
        except Exception as e:
            err = str(e)
            # 429 → API xác nhận quota hết, đánh dấu để bỏ qua tier này trong session
            if "RESOURCE_EXHAUSTED" in err or "429" in err or "quota" in err.lower():
                logger.info(f"[{user_id}] Tier {i} ({model}) API quota exhausted, marking + falling back")
                quota_tracker.mark_exhausted(user_id, model)
            else:
                logger.warning(f"[{user_id}] Tier {i} ({model}) failed: {e}. Trying next tier")
            continue

    return (
        "⚠️ Tại hạ đã thử qua tất cả tier nhưng key của đại hiệp đã hết quota free tier hôm nay.\n"
        "• Gõ /status xem chi tiết\n"
        "• Hoặc đợi reset (RPM = 1 phút, RPD = 24h)\n"
        "• Hoặc upgrade key Gemini lên trả phí để dùng được Pro tier"
    ), None, "none"


async def chat(
    session: AsyncSession,
    user_id: int,
    db_history: list[dict],
    user_message: str,
    gemini_key: str,
    groq_key: str,
) -> tuple[str, str]:
    """Main entry point. Runs agentic loop with tool use. Returns (final_text, model_used)."""
    user_message = user_message[:MAX_INPUT_CHARS]
    complexity = classify(user_message)
    start_tier = COMPLEXITY_START[complexity]
    logger.info(f"[{user_id}] complexity={complexity} start_tier={start_tier} msg_len={len(user_message)}")

    messages: list[dict] = []
    for m in db_history[-(MAX_HISTORY_TURNS * 2):]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    last_model = "none"
    for step in range(MAX_AGENTIC_STEPS):
        text, tool_calls, model = await _call_with_fallback(
            user_id, messages, start_tier, gemini_key, groq_key,
        )
        last_model = model

        if not tool_calls:
            return text.strip() or "Tại hạ chưa rõ ý đại hiệp, xin nói lại cụ thể hơn.", last_model

        messages.append({"role": "assistant", "content": text, "tool_calls": tool_calls})

        for tc in tool_calls:
            logger.info(f"[{user_id}] Tool call: {tc['name']}({tc['input']})")
            result = await dispatch_tool(session, user_id, tc["name"], tc["input"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "tool_name": tc["name"],
                "result": result,
            })

    logger.warning(f"[{user_id}] Hit MAX_AGENTIC_STEPS={MAX_AGENTIC_STEPS}")
    return "Tại hạ đã xử lý xong nhưng cần thêm bước. Xin đại hiệp hỏi lại.", last_model
