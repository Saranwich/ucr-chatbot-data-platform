"""LLM seam (V2) — the ONLY file that imports the provider SDK (Gemini).

Swap providers/models here and nowhere else. Requirements: <10s latency,
function calling, strong Thai. Callers pass provider-neutral messages/tools;
all google.genai types stay inside this module.
"""
import os

from google import genai
from google.genai import types

# แลกได้บรรทัดเดียว — flash-lite ถูก/เร็วสุด (ดูคุณภาพตอน multi-turn)
MODEL = "gemini-3.1-flash-lite"

_client = None


def _get_client():
    # ponytail: lazy — import ไม่ต้องมี key, เฉพาะตอนเรียกจริงถึงต้องมี
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _to_contents(messages: list[dict]) -> list:
    # ponytail: coerce None/empty content → "" — a Part(text=None) is an empty
    # oneof and Gemini 400s on it (e.g. a model turn that ended with no text).
    return [
        types.Content(role=m["role"], parts=[types.Part(text=m.get("content") or "")])
        for m in messages
    ]


def _to_tools(tools: list[dict] | None):
    # tools = plain dicts {name, description, parameters(JSON-schema-ish)} → SDK Tool
    if not tools:
        return None
    return [types.Tool(function_declarations=[types.FunctionDeclaration(**t)]) for t in tools]


async def chat(messages: list[dict], system: str | None = None,
               tools: list[dict] | None = None, tool_handler=None) -> str:
    """One turn. messages: [{"role": "user"|"model", "content": str}].

    If the model calls tool(s), run tool_handler(name, args) for each, feed the
    results back, and return the model's follow-up text. tool_handler is sync.
    """
    contents = _to_contents(messages)
    config = types.GenerateContentConfig(system_instruction=system, tools=_to_tools(tools))
    client = _get_client()

    resp = await client.aio.models.generate_content(model=MODEL, contents=contents, config=config)

    # ponytail: loop tool rounds — the model may split several record_complaint
    # calls across turns; keep feeding results until it returns a plain-text reply
    # (cap 5 so a misbehaving model can't spin forever).
    for _ in range(5):
        if not resp.function_calls:
            break
        contents.append(resp.candidates[0].content)  # the model's tool-call turn
        for fc in resp.function_calls:
            if tool_handler:
                tool_handler(fc.name, dict(fc.args))
            contents.append(types.Content(
                role="tool",
                parts=[types.Part.from_function_response(name=fc.name, response={"ok": True})],
            ))
        resp = await client.aio.models.generate_content(model=MODEL, contents=contents, config=config)

    return resp.text or ""  # model can end a tool turn with no text; caller supplies a fallback
