from uuid import UUID

from app.clients import psql, typhoon
from app.schemas.ai_config import AgentConfig
from app.schemas.turn import Turn
from app.services.config import ai_config

PROCESS = "services.ai"


def chatbot_session_to_messages (session: list[Turn]) -> list[dict]:
    """แปลงบทสนทนาของเราเป็นรูปที่ provider อ่านรู้เรื่อง

    Turn.role ใช้คำเดียวกับ OpenAI อยู่แล้ว (user / assistant / system)
    เลยยกมาตรง ๆ ส่วน content_type ไม่ได้ส่งไป โมเดลอ่านจาก content พอ
    """
    return [{"role": turn.role, "content": turn.content} for turn in session]


async def communicator_reply (session: list[Turn]) -> tuple[str | None, AgentConfig]:
    """ถามโมเดลว่าจะตอบอะไร — ตอนนี้มี provider เดียวคือ typhoon

    คืน config ที่ใช้ยิงรอบนั้นกลับไปด้วย คนเรียกจะได้เก็บลงฐานว่าคำตอบนี้ออกมาจากโมเดลตัวไหน
    """
    config = ai_config.get().communicator
    if config.provider != "typhoon":
        await psql.create_and_save_log(PROCESS, f"communicator ตั้ง provider {config.provider} ที่ยังไม่รองรับ รอบนี้เลยเงียบ")
        return None, config

    # prompt ไม่เก็บลง session เอาไว้หน้าสุดตอนยิงทุกรอบ แก้ prompt แล้ว session ที่คุยค้างได้ของใหม่ทันที
    messages = chatbot_session_to_messages(session)
    if config.prompt:
        messages = [{"role": "system", "content": config.prompt}, *messages]

    reply = await typhoon.chat(
        messages,
        config.model_name,
        config.temperature,
        config.max_output_tokens,
    )
    if reply is None:
        await psql.create_and_save_log(PROCESS, "ไม่มี provider ไหนตอบได้ รอบนี้เลยเงียบ")
    return reply, config

def conversation_to_transcript (conversation: list[Turn]) -> str:
    """ปั้นบทสนทนาเป็นข้อความก้อนเดียวให้ analyzer อ่าน

    ไม่ส่งเป็น messages หลายตาแบบตอนคุย เพราะ analyzer ไม่ได้คุยต่อ มันอ่านของที่จบแล้ว
    ส่งเป็นบทสนทนาหลายตาเมื่อไหร่ โมเดลจะนึกว่าถึงตามันตอบชาวบ้าน แล้วเขียนคำถามออกมาแทนบทสรุป
    """
    name = {"user": "ชาวบ้าน", "assistant": "บอท"}
    return "\n".join(f"{name.get(turn.role, turn.role)}: {turn.content}" for turn in conversation)


async def analyzer (session_id: UUID) -> tuple[str | None, AgentConfig]:
    """อ่านบทสนทนาที่จบแล้วจากฐาน แล้วสรุปว่าได้เรื่องอะไรมาบ้าง — รอบนี้คืนเป็นข้อความเปล่า ยังไม่บันทึก"""
    config = ai_config.get().analyzer
    if config.provider != "typhoon":
        await psql.create_and_save_log(PROCESS, f"analyzer ตั้ง provider {config.provider} ที่ยังไม่รองรับ รอบนี้เลยข้าม")
        return None, config

    conversation = await psql.get_conversation(session_id)
    if not conversation:
        await psql.create_and_save_log(PROCESS, f"session {session_id} ไม่มีบทสนทนาในฐาน ไม่มีอะไรให้วิเคราะห์")
        return None, config

    messages = [{"role": "user", "content": conversation_to_transcript(conversation)}]
    if config.prompt:
        messages = [{"role": "system", "content": config.prompt}, *messages]

    result = await typhoon.chat(
        messages,
        config.model_name,
        config.temperature,
        config.max_output_tokens,
    )
    if result is None:
        await psql.create_and_save_log(PROCESS, f"session {session_id} วิเคราะห์ไม่สำเร็จ โมเดลไม่ตอบ")
    return result, config