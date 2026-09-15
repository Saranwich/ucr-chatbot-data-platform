"""ตัวต่อสายไปหา google ai studio — ยิงผ่านหน้า openai-compatible ของกูเกิลเอง

เลือกหน้า openai-compatible ไม่ใช่ทางเดิมของกูเกิล (generateContent/interactions)
เพราะที่นี่ต้องเสียบแทน typhoon ได้ตรง ๆ คนเรียกคือ services/ai ที่พูดภาษา openai อยู่แล้ว
เดินทางเดิมของกูเกิลแปลว่าต้องแปลขาไปขากลับทั้ง contents/parts/functionCall ซึ่งเป็นงานที่ไม่มีใครขอ

เลย์เอาต์ในไฟล์เหมือน clients/typhoon ทุกตัว ชื่อฟังก์ชัน พารามิเตอร์ และค่าที่คืนตรงกันหมด
ตั้งใจให้สลับ provider ได้ด้วยการเปลี่ยนชื่อโมดูลที่ import อย่างเดียว

ข้อควรระวังของกูเกิลที่ typhoon ไม่มี — thought signature:
โมเดลตระกูล gemini 3 แนบลายเซ็นความคิดมากับ tool call ที่ช่อง
extra_content.google.thought_signature แล้วบังคับให้ส่งกลับไปเหมือนเดิมในตาถัดไป
ขาดเมื่อไหร่มันตอบ 400 ทั้งคำขอ ที่นี่จึงคืน tool_calls ทั้งก้อนตามที่ได้มา ไม่แกะไม่ปั้นใหม่
ใครจะไปกรองช่องใน tool_calls ทีหลัง ให้รู้ว่ากำลังตัดของที่ต้องส่งกลับ
"""

import httpx

from app.clients import psql
from app.core.config import GOOGLE_AI_API_ENDPOINT, GOOGLE_AI_API_KEY

PROCESS_NAME = "clients.google_ai" #use for logs

TIMEOUT = 30


async def _post_chat_completions (body: dict) -> dict | None:
    """ยิง body ที่ปั้นเสร็จแล้วไปที่ /chat/completions คืน json ทั้งก้อน ไม่ 200 ก็ log แล้วคืน None

    ตัวนี้ไม่แกะ choices ให้ เพราะคนเรียกสองคนอยากได้คนละชิ้นจากก้อนเดียวกัน
    ไม่ครอบ try ไว้ที่นี่ ให้ httpx โยนขึ้นไปตามเดิม คนเรียกแต่ละคนตัดสินใจเองว่าจะรับหรือปล่อย

    เช็คคีย์ก่อนยิงเพราะยังไม่มีใครบังคับให้ตั้งตอนเปิดแอป เครื่องที่ยังไม่ได้ตั้งจะได้เห็น log
    ว่าขาดคีย์ ไม่ใช่เห็น 401 จากกูเกิลแล้วไปไล่หาว่าคีย์ผิดหรือโดนแบน
    """
    if not GOOGLE_AI_API_KEY:
        await psql.create_and_save_log(PROCESS_NAME, "ยังไม่ได้ตั้ง GOOGLE_AI_API_KEY ใน .env เลยยิงไม่ได้")
        return None

    headers = {"Authorization": f"Bearer {GOOGLE_AI_API_KEY}"}

    async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
        resp = await cli.post(
            f"{GOOGLE_AI_API_ENDPOINT}/chat/completions", headers=headers, json=body
        )

    if resp.status_code != 200:
        await psql.create_and_save_log(
            PROCESS_NAME, f"google ai ไม่ตอบ {resp.status_code} {resp.text}"
        )
        return None

    return resp.json()


async def chat (
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    response_format: dict | None = None,
) -> str | None:
    """ถามโมเดลเอาข้อความเปล่า ๆ หนึ่งก้อน — ทางเดียวกับ typhoon.chat

    response_format คือคำขอให้คายเป็น JSON ตามรูปที่กำหนด ใส่หรือไม่ใส่ก็ได้
    ฝั่งกูเกิลบังคับตามจริง ต่างจาก typhoon ที่ทิ้งช่องนี้เงียบ ๆ — รูปที่ขอไปคือรูปที่ได้กลับมา
    """
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if response_format is not None:
        body["response_format"] = response_format

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

    tool_choice ส่งต่อไปตามที่คนเรียกสั่ง หน้า openai-compatible แปลให้เป็น
    function_calling_config ของกูเกิล (auto / any / none) เอง
    ช่องที่มันไม่รู้จักมันจะทิ้งเงียบ ๆ ไม่ฟ้อง อย่าอ่านการไม่ error ว่าเป็นการรองรับ

    ครอบ try ไว้เหมือน typhoon เพราะคนเรียกคือตัวกวาดที่รันอยู่หลังบ้าน
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
        await psql.create_and_save_log(PROCESS_NAME, f"google ai ยิงไม่ถึง {type(error).__name__} {error}")
        return None

    if data is None:
        return None

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as error:
        await psql.create_and_save_log(PROCESS_NAME, f"google ai ตอบมาในรูปที่อ่านไม่ออก {type(error).__name__} {error}")
        return None

    if not isinstance(message, dict):
        await psql.create_and_save_log(PROCESS_NAME, f"google ai ตอบ message ที่ไม่ใช่ก้อนข้อมูล {type(message).__name__}")
        return None

    return message
