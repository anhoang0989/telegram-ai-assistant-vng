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
from src.ai.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Cache clients per api_key — tạo Client mới mỗi call gây latency 200-500ms
_GEMINI_CLIENTS: dict[str, "genai.Client"] = {}
_GROQ_CLIENTS: dict[str, AsyncGroq] = {}


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
) -> tuple[str, list[dict] | None]:
    client = _get_gemini_client(api_key)
    contents = _messages_to_gemini_contents(messages)
    config = gtypes.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
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

def _messages_to_groq_format(messages: list[dict]) -> list[dict]:
    out = [{"role": "system", "content": SYSTEM_PROMPT}]
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
) -> tuple[str, list[dict] | None]:
    client = _get_groq_client(api_key)
    groq_messages = _messages_to_groq_format(messages)
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
