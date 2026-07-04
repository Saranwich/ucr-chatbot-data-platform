"""AI conversation core (V2).

# ponytail: step 2 (#89) — real Gemini via services/llm, hardcoded prompt
# "who are you" to prove the LLM call (Thai + latency). Steps 3-6 add the
# personality system prompt, Redis memory, and 4-field report extraction;
# user_text becomes the real prompt input then.
"""
from app.services.llm import get_response


async def build_question(user_text: str) -> str:
    return await get_response([{"role": "user", "content": "who are you"}])
