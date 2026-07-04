"""LLM seam (V2) — the ONLY file that imports the provider SDK (Gemini Flash).

Swap providers here and nowhere else. Requirements: <10s latency, function
calling, strong Thai.

# ponytail: stub; step 2 (#89) implements get_response() against Gemini.
"""


async def get_response(messages) -> str:
    raise NotImplementedError  # step 2 (#89)
