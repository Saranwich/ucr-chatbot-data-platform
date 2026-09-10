from app.clients import psql, typhoon
from app.schemas.turn import Turn

PROCESS = "services.ai"


def chatbot_session_to_messages (session: list[Turn]) -> list[dict]:
    """แปลงบทสนทนาของเราเป็นรูปที่ provider อ่านรู้เรื่อง

    Turn.role ใช้คำเดียวกับ OpenAI อยู่แล้ว (user / assistant / system)
    เลยยกมาตรง ๆ ส่วน content_type ไม่ได้ส่งไป โมเดลอ่านจาก content พอ
    """
    return [{"role": turn.role, "content": turn.content} for turn in session]


async def communicator_reply (session: list[Turn]) -> str | None:
    """ถามโมเดลว่าจะตอบอะไร — ตอนนี้มี provider เดียวคือ typhoon"""
    reply = await typhoon.chat(chatbot_session_to_messages(session))
    if reply is None:
        await psql.create_and_save_log(PROCESS, "ไม่มี provider ไหนตอบได้ รอบนี้เลยเงียบ")
    return reply
