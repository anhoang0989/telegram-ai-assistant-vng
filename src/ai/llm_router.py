"""
LLM Router + Agentic Loop.

Flow:
  1. Build messages từ DB history + tin nhắn mới
  2. Gọi LLM (tier thấp nhất phù hợp với complexity)
  3. Nếu LLM trả tool_calls → execute → feed kết quả ngược lại → gọi LLM lại
  4. Lặp đến khi LLM không gọi tool nữa, trả về text cuối cùng cho user

Tier fallback: quota hết của model nào → nhảy sang model tier kế tiếp trong chuỗi.
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

MAX_INPUT_CHARS = 8000  # tăng để nhận được meeting transcript
MAX_HISTORY_TURNS = 20
MAX_AGENTIC_STEPS = 5   # an toàn — tránh vòng lặp tool vô hạn

TIERS = [
    {"model": settings.model_tier1, "provider": "gemini"},
    {"model": settings.model_tier2, "provider": "gemini"},
    {"model": settings.model_tier3, "provider": "gemini"},
    {"model": settings.model_tier4, "provider": "groq"},
]


async def _call_tier(tier: dict, messages: list[dict]) -> tuple[str, list[dict] | None]:
    if tier["provider"] == "gemini":
        return await call_gemini(tier["model"], messages, TOOLS)
    return await call_groq(tier["model"], messages, TOOLS)


async def _call_with_fallback(
    messages: list[dict],
    start_tier: int,
) -> tuple[str, list[dict] | None, str]:
    """Try tiers from start_tier downward until one succeeds. Returns (text, tool_calls, model_used)."""
    for i in range(start_tier, len(TIERS)):
        tier = TIERS[i]
        model = tier["model"]

        if not quota_tracker.available(model):
            logger.info(f"Tier {i} ({model}) quota exhausted, falling back")
            continue

        try:
            quota_tracker.record(model)
            text, tool_calls = await _call_tier(tier, messages)
            return text, tool_calls, model
        except Exception as e:
            logger.warning(f"Tier {i} ({model}) failed: {e}. Trying next tier")
            continue

    return "⚠️ Tất cả AI providers đang bận. Thử lại sau nhé.", None, "none"


async def chat(
    session: AsyncSession,
    db_history: list[dict],
    user_message: str,
) -> tuple[str, str]:
    """
    Main entry point. Runs agentic loop with tool use.
    Returns (final_text, model_used).
    """
    user_message = user_message[:MAX_INPUT_CHARS]
    complexity = classify(user_message)
    start_tier = COMPLEXITY_START[complexity]
    logger.info(f"complexity={complexity} start_tier={start_tier} msg_len={len(user_message)}")

    # Build working messages list (will grow during agentic loop)
    messages: list[dict] = []
    for m in db_history[-(MAX_HISTORY_TURNS * 2):]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    last_model = "none"
    for step in range(MAX_AGENTIC_STEPS):
        text, tool_calls, model = await _call_with_fallback(messages, start_tier)
        last_model = model

        if not tool_calls:
            # Done — LLM gave final text response
            return text.strip() or "Tao chưa rõ ý mày, nói lại cụ thể hơn nhé?", last_model

        # Record assistant's turn with tool calls
        messages.append({"role": "assistant", "content": text, "tool_calls": tool_calls})

        # Execute each tool and append result
        for tc in tool_calls:
            logger.info(f"Tool call: {tc['name']}({tc['input']})")
            result = await dispatch_tool(session, tc["name"], tc["input"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "tool_name": tc["name"],
                "result": result,
            })

        # After first tool call, subsequent calls can stay on same tier
        # (don't re-run classifier — we're in an agentic flow)

    # If we hit max steps, return whatever text we have
    logger.warning(f"Hit MAX_AGENTIC_STEPS={MAX_AGENTIC_STEPS}")
    return "Tao đã xử lý xong nhưng cần thêm bước. Thử hỏi lại nhé.", last_model
