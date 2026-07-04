"""AI conversation core (V2). Stub — the real flow arrives step by step.

# ponytail: empty seam. Step 1 (#88) wires build_question() into the LINE
# pipe with a hardcoded reply; steps 2-6 add Gemini (via services/llm),
# Redis memory, and the 4-field report extraction.
"""


async def build_question(*args, **kwargs) -> str:
    raise NotImplementedError  # step 1 (#88)
