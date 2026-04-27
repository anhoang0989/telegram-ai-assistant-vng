"""
LLM Router + Agentic Loop (BYOK edition).

Flow:
  1. Build messages từ DB history + tin nhắn mới
  2. Gọi LLM (tier thấp nhất phù hợp với complexity)
  3. Nếu LLM trả tool_calls → execute → feed kết quả ngược lại → gọi LLM lại
  4. Lặp đến khi LLM không gọi tool nữa, trả về text cuối cùng cho user

Quota + keys phân theo user_id → mỗi người free tier riêng.
Tier với provider thiếu key (groq/claude) sẽ được skip tự động.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.ai.classifier import classify, COMPLEXITY_START
from src.ai.quota_tracker import quota_tracker
from src.ai.providers import call_gemini, call_groq, call_claude
from src.ai.prompts import build_system_prompt
from src.ai.tools import TOOLS
from src.bot.tool_dispatcher import dispatch_tool

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 8000
MAX_HISTORY_TURNS = 10  # giảm từ 20 (v0.9.4) — giảm token, tăng tốc 30-50%
MAX_AGENTIC_STEPS = 5

TIERS = [
    {"model": settings.llm_tier1, "provider": "gemini"},  # 3-flash-lite — workhorse
    {"model": settings.llm_tier2, "provider": "gemini"},  # 2.5-flash-lite — backup
    {"model": settings.llm_tier3, "provider": "gemini"},  # 3-flash — reasoning
    {"model": settings.llm_tier4, "provider": "gemini"},  # 2.5-flash — backup reasoning
    {"model": settings.llm_tier5, "provider": "groq"},    # llama — cross-provider backup
    {"model": settings.llm_tier6, "provider": "gemini"},  # 3-pro — paid only
    {"model": settings.llm_tier7, "provider": "gemini"},  # 2.5-pro — paid only
    {"model": settings.llm_tier8, "provider": "claude"},  # claude haiku — paid optional
    {"model": settings.llm_tier9, "provider": "claude"},  # claude sonnet — paid optional
]


async def _call_tier(
    tier: dict,
    messages: list[dict],
    keys: dict[str, str | None],
    system_prompt: str | None = None,
) -> tuple[str, list[dict] | None]:
    provider = tier["provider"]
    if provider == "gemini":
        return await call_gemini(keys["gemini"], tier["model"], messages, TOOLS, system_override=system_prompt)
    if provider == "groq":
        return await call_groq(keys["groq"], tier["model"], messages, TOOLS, system_override=system_prompt)
    if provider == "claude":
        return await call_claude(keys["claude"], tier["model"], messages, TOOLS, system_override=system_prompt)
    raise ValueError(f"Unknown provider: {provider}")


async def _call_with_fallback(
    user_id: int,
    messages: list[dict],
    start_tier: int,
    keys: dict[str, str | None],
    system_prompt: str | None = None,
) -> tuple[str, list[dict] | None, str]:
    for i in range(start_tier, len(TIERS)):
        tier = TIERS[i]
        model = tier["model"]
        provider = tier["provider"]

        # Skip tier nếu user chưa nhập key cho provider tương ứng
        if not keys.get(provider):
            logger.debug(f"[{user_id}] Tier {i} ({model}) skipped — no {provider} key")
            continue

        if not quota_tracker.available(user_id, model):
            logger.info(f"[{user_id}] Tier {i} ({model}) quota exhausted (local), falling back")
            continue

        try:
            text, tool_calls = await _call_tier(tier, messages, keys, system_prompt)
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
        "• Hoặc upgrade key Gemini lên trả phí, hoặc thêm Claude key (gõ /setkey)"
    ), None, "none"


def _find_tier_index(model_id: str) -> int | None:
    for i, t in enumerate(TIERS):
        if t["model"] == model_id:
            return i
    return None


async def _call_pinned(
    user_id: int,
    messages: list[dict],
    model_id: str,
    keys: dict[str, str | None],
    system_prompt: str | None = None,
) -> tuple[str, list[dict] | None, str]:
    """User đã pin 1 model cụ thể qua /model — KHÔNG fallback sang tier khác.
    Quota hết hoặc thiếu key → báo lỗi rõ ràng để user tự xử lý.
    """
    idx = _find_tier_index(model_id)
    if idx is None:
        return (
            f"⚠️ Model pinned `{model_id}` không nằm trong list. Gõ /model để chọn lại.",
            None, "none",
        )
    tier = TIERS[idx]
    provider = tier["provider"]

    if not keys.get(provider):
        return (
            f"⚠️ Đại hiệp đã pin model `{model_id}` (provider {provider}) "
            f"nhưng chưa nhập {provider} key. Gõ /setkey hoặc /model để đổi.",
            None, "none",
        )

    if not quota_tracker.available(user_id, model_id):
        return (
            f"⚠️ Model pinned `{model_id}` đã hết quota local cho hôm nay.\n"
            "Gõ /model để chuyển sang Auto (có fallback) hoặc đổi model khác.",
            None, "none",
        )

    try:
        text, tool_calls = await _call_tier(tier, messages, keys, system_prompt=system_prompt)
        quota_tracker.record(user_id, model_id)
        return text, tool_calls, model_id
    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "429" in err or "quota" in err.lower():
            quota_tracker.mark_exhausted(user_id, model_id)
            return (
                f"⚠️ Model pinned `{model_id}` API trả 429 (hết quota).\n"
                "Gõ /model để chuyển sang Auto hoặc đổi model.",
                None, "none",
            )
        logger.warning(f"[{user_id}] Pinned model {model_id} failed: {e}")
        return (
            f"⚠️ Model pinned `{model_id}` lỗi: `{e}`.\n"
            "Gõ /model để đổi sang Auto hoặc model khác.",
            None, "none",
        )


async def chat(
    session: AsyncSession,
    user_id: int,
    db_history: list[dict],
    user_message: str,
    gemini_key: str,
    groq_key: str | None = None,
    claude_key: str | None = None,
    preferred_model: str = "auto",
) -> tuple[str, str, list[str]]:
    """Main entry point. Runs agentic loop with tool use.
    Returns (final_text, model_used, tool_names_called).

    tool_names_called là list TÊN tool LLM đã thực sự gọi trong loop —
    chat_handler dùng để detect fake-confirm hallucination (LLM nói "đã lưu/đặt"
    mà không có tool save/create nào fire → là fake).

    preferred_model:
      - 'auto'    → smart 7+2 tier fallback (default)
      - <model_id> → pinned, KHÔNG fallback sang tier khác
    """
    user_message = user_message[:MAX_INPUT_CHARS]
    complexity = classify(user_message)
    start_tier = COMPLEXITY_START[complexity]
    pinned = preferred_model and preferred_model != "auto"

    # v0.9.4: build dynamic system prompt với current VN time
    # → fix bug LLM tính sai "2 tiếng nữa", "mai", "thứ 6 tuần sau"
    system_prompt = build_system_prompt()

    logger.info(
        f"[{user_id}] complexity={complexity} start_tier={start_tier} "
        f"msg_len={len(user_message)} pinned={preferred_model if pinned else 'no'}"
    )

    keys = {"gemini": gemini_key, "groq": groq_key, "claude": claude_key}

    messages: list[dict] = []
    for m in db_history[-(MAX_HISTORY_TURNS * 2):]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    last_model = "none"
    tool_names_called: list[str] = []
    for step in range(MAX_AGENTIC_STEPS):
        if pinned:
            text, tool_calls, model = await _call_pinned(
                user_id, messages, preferred_model, keys, system_prompt=system_prompt,
            )
        else:
            text, tool_calls, model = await _call_with_fallback(
                user_id, messages, start_tier, keys, system_prompt=system_prompt,
            )
        last_model = model

        if not tool_calls:
            return (
                text.strip() or "Tại hạ chưa rõ ý đại hiệp, xin nói lại cụ thể hơn.",
                last_model,
                tool_names_called,
            )

        messages.append({"role": "assistant", "content": text, "tool_calls": tool_calls})

        for tc in tool_calls:
            tool_names_called.append(tc["name"])
            logger.info(f"[{user_id}] Tool call: {tc['name']}({tc['input']})")
            result = await dispatch_tool(session, user_id, tc["name"], tc["input"])
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "tool_name": tc["name"],
                "result": result,
            })

    logger.warning(f"[{user_id}] Hit MAX_AGENTIC_STEPS={MAX_AGENTIC_STEPS}")
    return (
        "Tại hạ đã xử lý xong nhưng cần thêm bước. Xin đại hiệp hỏi lại.",
        last_model,
        tool_names_called,
    )
