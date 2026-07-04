"""LLM seam (V2) — the ONLY file that imports the provider SDK (Gemini).

Swap providers/models here and nowhere else. Requirements: <10s latency,
function calling, strong Thai.

# ponytail: step 2 (#89) — single-turn text. System prompt, memory and
# function-calling extend get_response() in later steps.
"""
import os

from google import genai
from google.genai import types

# แลกได้บรรทัดเดียว — flash-lite ถูก/เร็วสุด (ดูคุณภาพตอน step 5 multi-turn)
MODEL = "gemini-2.5-flash-lite"

_client = None


def _get_client():
    # ponytail: lazy — import ไม่ต้องมี key, เฉพาะตอนเรียกจริงถึงต้องมี
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


async def get_response(messages: list[dict], system: str | None = None) -> str:
    """messages: [{"role": "user"|"model", "content": str}, ...] -> reply text."""
    contents = [
        types.Content(role=m["role"], parts=[types.Part(text=m["content"])])
        for m in messages
    ]
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    resp = await _get_client().aio.models.generate_content(
        model=MODEL, contents=contents, config=config
    )
    return resp.text
