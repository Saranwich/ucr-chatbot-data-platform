import httpx

from app.clients import psql
from app.core.config import LINE_CHANNEL_ACCESS_TOKEN

PROCESS_NAME = "clinents.line" #use for logs

REPLY_URL = "https://api.line.me/v2/bot/message/reply"
TIMEOUT = 10


async def replie (replytoken: str, messages: list[str]) -> int:

    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    body = {
        "replyToken": replytoken,
        "messages": [{"type": "text", "text": text} for text in messages[:5]],
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
        resp = await cli.post(REPLY_URL, headers=headers, json=body)

    if resp.status_code != 200:
        await psql.create_and_save_log(
            PROCESS_NAME, f"ตอบกลับไม่สำเร็จ {resp.status_code} {resp.text}"
        )
    await psql.create_and_save_log(PROCESS_NAME, f"ตอบกลับสำเร็จ {resp.status_code} {resp.text}")
    return resp.status_code #status code
