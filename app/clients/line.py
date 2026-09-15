from uuid import UUID

import httpx

from app.clients import psql
from app.core.config import (
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CONTENT_URL,
    LINE_LOADING_URL,
    LINE_PUSH_URL,
    LINE_REPLY_URL,
)

PROCESS_NAME = "clinents.line" #use for logs

TIMEOUT = 10

# ไลน์รับเฉพาะ 5-60 และต้องเป็นจำนวนเท่าของ 5 — รอบที่ช้าสุดเท่าที่วัดได้คือ 12 วิ
# เผื่อไว้เกินไม่เสียหาย จุดหายเองทันทีที่ข้อความจริงไปถึง ไม่ต้องสั่งหยุด
LOADING_SECONDS = 30


async def replie (replytoken: str, messages: list[str], quick_replies: list[dict] | None = None) -> int:

    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    message_objects = [{"type": "text", "text": text} for text in messages[:5]]
    if quick_replies and message_objects:
        items = []
        for reply in quick_replies[:13]:
            action = {"type": reply["type"], "label": reply["label"]}
            if reply["type"] == "message":
                action["text"] = reply["text"]
            items.append({"type": "action", "action": action})
        message_objects[-1]["quickReply"] = {"items": items}
    body = {
        "replyToken": replytoken,
        "messages": message_objects,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
        resp = await cli.post(LINE_REPLY_URL, headers=headers, json=body)

    if resp.status_code != 200:
        await psql.create_and_save_log(
            PROCESS_NAME, f"ตอบกลับไม่สำเร็จ {resp.status_code} {resp.text}"
        )
    await psql.create_and_save_log(PROCESS_NAME, f"ตอบกลับสำเร็จ {resp.status_code} {resp.text}")
    return resp.status_code #status code


async def push (line_user_id: str, messages: list[str], retry_key: UUID | None = None) -> int:
    """ยิงข้อความหาคนคนเดียวโดยไม่ต้องมี replytoken

    retry_key ให้ไลน์รู้ว่าเป็นคำขอเดิม ยิงซ้ำด้วยคีย์เดิมจะไม่ส่งซ้ำถึงชาวบ้าน
    """
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    if retry_key is not None:
        headers["X-Line-Retry-Key"] = str(retry_key)
    body = {
        "to": line_user_id,
        "messages": [{"type": "text", "text": text} for text in messages[:5]],
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
        resp = await cli.post(LINE_PUSH_URL, headers=headers, json=body)

    if resp.status_code != 200:
        await psql.create_and_save_log(
            PROCESS_NAME, f"ยิงข้อความไม่สำเร็จ {resp.status_code} {resp.text}"
        )
    return resp.status_code


async def start_loading (line_user_id: str) -> None:
    """ขึ้นจุดสามจุดในแชทของคนคนนั้น บอกว่ากำลังคิดอยู่ ไม่ได้เงียบใส่

    ครอบ try ไว้ทั้งก้อนเพราะนี่เป็นของประดับ ล้มยังไงก็ห้ามพาคำตอบล้มตาม
    ชาวบ้านไม่เห็นจุดยังคุยต่อได้ แต่ไม่ได้คำตอบคือจบ

    ใช้ได้เฉพาะแชทตัวต่อตัว กลุ่มกับห้องหลายคนไลน์ไม่รองรับ — โปรเจกต์นี้มีแต่แชทตัวต่อตัวอยู่แล้ว
    """
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {"chatId": line_user_id, "loadingSeconds": LOADING_SECONDS}

    # ดักกว้างกว่าที่อื่นในไฟล์นี้โดยตั้งใจ ที่อื่นล้มแล้วชาวบ้านเสียของจริง ที่นี่เสียแค่จุดสามจุด
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
            resp = await cli.post(LINE_LOADING_URL, headers=headers, json=body)
        if resp.status_code != 202:
            await psql.create_and_save_log(
                PROCESS_NAME, f"ขึ้นจุดโหลดไม่สำเร็จ {resp.status_code} {resp.text}"
            )
    except Exception as error:
        await psql.create_and_save_log(PROCESS_NAME, f"ขึ้นจุดโหลดไม่ได้ {type(error).__name__} {error}")


async def get_image_content (message_id: str) -> tuple[str, bytes | None, str]:
    """โหลดไฟล์รูปจากไลน์ คืน (ที่อยู่รูปฝั่งไลน์, ตัวไฟล์, ชนิดไฟล์)

    ที่อยู่คืนให้เสมอแม้โหลดไม่สำเร็จ เพราะยังเก็บลง db ไว้ตามเก็บใหม่ได้ตราบที่ไลน์ยังไม่ลบ
    โหลดไม่ได้ = ตัวไฟล์เป็น None — ไลน์เก็บรูปให้ชั่วคราว ปล่อยไว้นานแล้วค่อยมาโหลดจะไม่เจอ
    """
    url = LINE_CONTENT_URL.format(message_id=message_id)
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}

    async with httpx.AsyncClient(timeout=TIMEOUT) as cli:
        resp = await cli.get(url, headers=headers)

    if resp.status_code != 200:
        await psql.create_and_save_log(
            PROCESS_NAME, f"โหลดรูป {message_id} ไม่สำเร็จ {resp.status_code} {resp.text}"
        )
        return url, None, ""

    return url, resp.content, resp.headers.get("content-type", "")
