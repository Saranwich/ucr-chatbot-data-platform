"""AI conversation core (V2).

# ponytail: step 1 (#88) — build_question() returns a hardcoded reply to prove
# the LINE pipe. Steps 2-6 swap in Gemini (via services/llm), Redis memory, and
# the 4-field report extraction; user_text becomes the real prompt input then.
"""


async def build_question(user_text: str) -> str:
    return "AI question here"
