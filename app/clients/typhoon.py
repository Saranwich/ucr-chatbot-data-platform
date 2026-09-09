import httpx

from app.clients import psql
from app.core.config import TYPHOON_API_ENDPOINT, TYPHOON_API_KEY, TYPHOON_MODEL

PROCESS_NAME = "clients.typhoon" #use for logs

TIMEOUT = 30


async def chat (messages: list[dict]) -> str | None:
    headers = {"Authorization": f"Bearer {TYPHOON_API_KEY}"}
    body = {
        "model": TYPHOON_MODEL,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
        resp = await cli.post(
            f"{TYPHOON_API_ENDPOINT}/chat/completions", headers=headers, json=body
        )

    if resp.status_code != 200:
        await psql.create_and_save_log(
            PROCESS_NAME, f"typhoon ไม่ตอบ {resp.status_code} {resp.text}"
        )
        return None
    #log ด้วย
    return resp.json()["choices"][0]["message"]["content"]
