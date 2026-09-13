"""ตัวต่อสายไปหา typhoon — endpoint เดียว /chat/completions แต่เรียกได้สองแบบ

chat() เป็นทางข้อความล้วนสำหรับ caller ที่ไม่ใช้ tool
chat_with_tools() ใช้ตอนให้โมเดลสั่งงานแอป ต้องคืน message ทั้งก้อนเพราะ tool_calls อยู่ข้าง ๆ content
สองตัวใช้ body คนละหน้าตาแต่ยิงที่เดียวกัน เลยแยกตัวยิงออกมาเป็นตัวกลางให้ใช้ร่วมกัน
"""

import httpx

from app.clients import psql
from app.core.config import TYPHOON_API_ENDPOINT, TYPHOON_API_KEY

PROCESS_NAME = "clients.typhoon" #use for logs

TIMEOUT = 30


async def _post_chat_completions (body: dict) -> dict | None:
    """ยิง body ที่ปั้นเสร็จแล้วไปที่ /chat/completions คืน json ทั้งก้อน ไม่ 200 ก็ log แล้วคืน None

    ตัวนี้ไม่แกะ choices ให้ เพราะคนเรียกสองคนอยากได้คนละชิ้นจากก้อนเดียวกัน
    ไม่ครอบ try ไว้ที่นี่ ให้ httpx โยนขึ้นไปตามเดิม คนเรียกแต่ละคนตัดสินใจเองว่าจะรับหรือปล่อย
    """
    headers = {"Authorization": f"Bearer {TYPHOON_API_KEY}"}

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
    return resp.json()


async def chat (messages: list[dict], model: str, temperature: float, max_tokens: int) -> str | None:
    """ถามโมเดลเอาข้อความเปล่า ๆ หนึ่งก้อน — ทางที่ communicator ใช้อยู่"""
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    data = await _post_chat_completions(body)
    if data is None:
        return None

    return data["choices"][0]["message"]["content"]


async def chat_with_tools (
    messages: list[dict],
    tools: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    tool_choice: str | dict = "auto",
) -> dict | None:
    """ถามโมเดลโดยยื่นรายการ tool ให้เลือกใช้ คืน message ทั้งก้อน พังก็คืน None

    ห้ามคืนแต่ content เพราะของที่คนเรียกอยากได้จริงคือ tool_calls ที่อยู่ในก้อนเดียวกัน
    รอบที่มันสั่ง tool ช่อง content มักว่างหรือเป็น None การคืน content อย่างเดียวจะกลายเป็น "ไม่ตอบ"
    tool_choice เลือกได้ตามงาน: analyzer ใช้ auto แล้วตรวจเอง ส่วน communicator ใช้ required
    เพื่อบังคับคืน boolean ทุกตา และใช้ none ในรอบตอบหลัง tool ทำงาน

    ตัวนี้ครอบ try ไว้ ต่างจาก chat() เพราะคนเรียกคือตัวกวาดที่รันอยู่หลังบ้าน
    เน็ตสะดุดครั้งเดียวแล้วโยนทะลุขึ้นไป session จะค้างสถานะ pending ไปตลอด ไม่มีใครมาลองใหม่
    """
    body = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # ValueError กิน json.JSONDecodeError ด้วย — 200 แต่ตัว body ไม่ใช่ json ก็มาลงตรงนี้
    try:
        data = await _post_chat_completions(body)
    except (httpx.HTTPError, ValueError) as error:
        await psql.create_and_save_log(PROCESS_NAME, f"typhoon ยิงไม่ถึง {type(error).__name__} {error}")
        return None

    if data is None:
        return None

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as error:
        await psql.create_and_save_log(PROCESS_NAME, f"typhoon ตอบมาในรูปที่อ่านไม่ออก {type(error).__name__} {error}")
        return None

    if not isinstance(message, dict):
        await psql.create_and_save_log(PROCESS_NAME, f"typhoon ตอบ message ที่ไม่ใช่ก้อนข้อมูล {type(message).__name__}")
        return None

    return message
