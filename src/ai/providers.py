"""
Gemini (google-genai) + Groq wrappers — BYOK: keys passed per-call, not module-level.

Unified message format:
  [{"role": "user"|"assistant"|"tool", "content": str, "tool_calls": [...]?, "tool_call_id": str?}]

Each call returns (text: str, tool_calls: list[{name, id, input}] | None).
"""
import json
import logging
import uuid
from google import genai
from google.genai import types as gtypes
from groq import AsyncGroq
from anthropic import AsyncAnthropic
from src.ai.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Cache clients per api_key — tạo Client mới mỗi call gây latency 200-500ms
_GEMINI_CLIENTS: dict[str, "genai.Client"] = {}
_GROQ_CLIENTS: dict[str, AsyncGroq] = {}
_CLAUDE_CLIENTS: dict[str, AsyncAnthropic] = {}


def _get_gemini_client(api_key: str) -> "genai.Client":
    client = _GEMINI_CLIENTS.get(api_key)
    if client is None:
        client = genai.Client(api_key=api_key)
        _GEMINI_CLIENTS[api_key] = client
    return client


def _get_groq_client(api_key: str) -> AsyncGroq:
    client = _GROQ_CLIENTS.get(api_key)
    if client is None:
        client = AsyncGroq(api_key=api_key)
        _GROQ_CLIENTS[api_key] = client
    return client


def _get_claude_client(api_key: str) -> AsyncAnthropic:
    client = _CLAUDE_CLIENTS.get(api_key)
    if client is None:
        client = AsyncAnthropic(api_key=api_key)
        _CLAUDE_CLIENTS[api_key] = client
    return client


def _to_gemini_tools(tools: list[dict]) -> list[gtypes.Tool]:
    declarations = []
    for t in tools:
        declarations.append(
            gtypes.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["input_schema"],
            )
        )
    return [gtypes.Tool(function_declarations=declarations)]


def _to_groq_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


# ========== GEMINI WEB SEARCH (grounded) ==========

async def gemini_web_search(api_key: str, query: str) -> dict:
    """
    Gọi Gemini với GoogleSearch grounding builtin → trả về text + nguồn.
    Tách riêng vì grounding tool không mix với function_declarations cùng request.
    """
    client = _get_gemini_client(api_key)
    config = gtypes.GenerateContentConfig(
        tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())],
        temperature=0.3,
    )
    # Dùng 2.5-flash — model rẻ nhất hỗ trợ grounding ổn định
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=query,
            config=config,
        )
    except Exception as e:
        # Fallback sang flash-lite nếu 2.5-flash hết quota
        logger.warning(f"web_search on 2.5-flash failed: {e}, retrying flash-lite")
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=query,
            config=config,
        )

    text = ""
    sources: list[str] = []
    try:
        text = response.text or ""
    except Exception:
        pass
    try:
        gm = response.candidates[0].grounding_metadata
        if gm and getattr(gm, "grounding_chunks", None):
            for ch in gm.grounding_chunks:
                web = getattr(ch, "web", None)
                if web and getattr(web, "uri", None):
                    sources.append(f"{web.title or web.uri} — {web.uri}")
    except Exception:
        pass

    return {"text": text, "sources": sources[:5]}


# ========== GEMINI ==========

def _messages_to_gemini_contents(messages: list[dict]) -> list[gtypes.Content]:
    contents = []
    for msg in messages:
        role = msg["role"]
        if role == "user":
            contents.append(gtypes.Content(role="user", parts=[gtypes.Part(text=msg["content"])]))
        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append(gtypes.Part(text=msg["content"]))
            for tc in msg.get("tool_calls", []):
                parts.append(gtypes.Part(
                    function_call=gtypes.FunctionCall(name=tc["name"], args=tc["input"])
                ))
            contents.append(gtypes.Content(role="model", parts=parts))
        elif role == "tool":
            contents.append(gtypes.Content(
                role="user",
                parts=[gtypes.Part(function_response=gtypes.FunctionResponse(
                    name=msg["tool_name"],
                    response=msg["result"] if isinstance(msg["result"], dict) else {"result": msg["result"]},
                ))],
            ))
    return contents


async def call_gemini(
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    system_override: str | None = None,
) -> tuple[str, list[dict] | None]:
    client = _get_gemini_client(api_key)
    contents = _messages_to_gemini_contents(messages)
    config = gtypes.GenerateContentConfig(
        system_instruction=system_override or SYSTEM_PROMPT,
        tools=_to_gemini_tools(tools) if tools else None,
        temperature=0.7,
    )
    response = await client.aio.models.generate_content(
        model=model, contents=contents, config=config,
    )

    tool_calls = []
    text_parts = []
    for part in response.candidates[0].content.parts:
        if getattr(part, "function_call", None):
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": part.function_call.name,
                "input": dict(part.function_call.args) if part.function_call.args else {},
            })
        elif getattr(part, "text", None):
            text_parts.append(part.text)

    return "".join(text_parts), tool_calls if tool_calls else None


# ========== GROQ ==========

def _messages_to_groq_format(messages: list[dict], system_override: str | None = None) -> list[dict]:
    out = [{"role": "system", "content": system_override or SYSTEM_PROMPT}]
    for msg in messages:
        role = msg["role"]
        if role == "user":
            out.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            entry = {"role": "assistant", "content": msg.get("content") or ""}
            if msg.get("tool_calls"):
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["input"])},
                    }
                    for tc in msg["tool_calls"]
                ]
            out.append(entry)
        elif role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": msg["tool_call_id"],
                "content": json.dumps(msg["result"]) if not isinstance(msg["result"], str) else msg["result"],
            })
    return out


async def call_groq(
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    system_override: str | None = None,
) -> tuple[str, list[dict] | None]:
    client = _get_groq_client(api_key)
    groq_messages = _messages_to_groq_format(messages, system_override=system_override)
    groq_tools = _to_groq_tools(tools) if tools else None

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=groq_messages,
            tools=groq_tools,
            tool_choice="auto" if groq_tools else None,
            temperature=0.7,
            max_tokens=2048,
        )
    except Exception as e:
        # Groq llama hay hallucinate tool name không có trong list → 400 tool_use_failed.
        # Retry không kèm tools để ít nhất trả lời text được.
        msg = str(e)
        if "tool_use_failed" in msg or "was not in request.tools" in msg:
            logger.warning(f"Groq tool hallucination on {model}, retrying without tools")
            response = await client.chat.completions.create(
                model=model,
                messages=groq_messages,
                temperature=0.7,
                max_tokens=2048,
            )
        else:
            raise

    choice = response.choices[0]
    text = choice.message.content or ""
    tool_calls = None
    if choice.message.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "input": json.loads(tc.function.arguments),
            }
            for tc in choice.message.tool_calls
        ]
    return text, tool_calls


# ========== CLAUDE (Anthropic) ==========

def _to_claude_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        }
        for t in tools
    ]


def _messages_to_claude_format(messages: list[dict]) -> list[dict]:
    """Convert unified format → Anthropic messages format.
    Claude: assistant message có thể chứa list[text|tool_use], user phản hồi tool qua tool_result.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role == "user":
            out.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            blocks = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for tc in msg.get("tool_calls", []) or []:
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
            # Claude assistant turn không được rỗng — fallback empty text
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            result = msg["result"]
            content_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            out.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": content_str,
                }],
            })
    return out


async def call_claude(
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    system_override: str | None = None,
) -> tuple[str, list[dict] | None]:
    client = _get_claude_client(api_key)
    claude_messages = _messages_to_claude_format(messages)
    claude_tools = _to_claude_tools(tools) if tools else None

    kwargs = {
        "model": model,
        "max_tokens": 2048,
        "system": system_override or SYSTEM_PROMPT,
        "messages": claude_messages,
        "temperature": 0.7,
    }
    if claude_tools:
        kwargs["tools"] = claude_tools

    response = await client.messages.create(**kwargs)

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for block in response.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text or "")
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "input": dict(block.input) if block.input else {},
            })
    return "".join(text_parts), tool_calls if tool_calls else None
