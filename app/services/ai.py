from uuid import UUID

from app.clients import psql, typhoon
from app.schemas.ai_config import AgentConfig
from app.schemas.turn import Turn
from app.services.ai_tools import (
    COMMUNICATOR_TOOL_SCHEMAS,
    SAVE_ANALYSE_PROTOCOL,
    SAVE_ANALYSE_TOOL,
    SET_FINISHED_PROTOCOL,
)
from app.services.config import ai_config

PROCESS = "services.ai"


def chatbot_session_to_messages (session: list[Turn]) -> list[dict]:
    """แปลงบทสนทนาของเราเป็นรูปที่ provider อ่านรู้เรื่อง

    Turn.role ใช้คำเดียวกับ OpenAI อยู่แล้ว (user / assistant / system)
    เลยยกมาตรง ๆ ส่วน content_type ไม่ได้ส่งไป โมเดลอ่านจาก content พอ
    """
    return [{"role": turn.role, "content": turn.content} for turn in session]


async def communicator_reply (session: list[Turn]) -> tuple[str | None, list[dict], AgentConfig]:
    """ถามโมเดลว่าจะตอบอะไร และคืน tool calls ให้ chatbot ลงมือหลังตอบ LINE

    คืน config ที่ใช้ยิงรอบนั้นกลับไปด้วย คนเรียกจะได้เก็บลงฐานว่าคำตอบนี้ออกมาจากโมเดลตัวไหน
    ยังไม่ลงมือตาม tool ตรงนี้ chatbot จะลงมือหลังบันทึกและส่งคำตอบแล้ว ป้องกัน runtime ปิด session แทรกกลางทาง

    ปกติจบในรอบเดียว — typhoon เขียนข้อความมาพร้อม tool_calls ก้อนเดียวกันเป็นส่วนใหญ่
    จะยิงรอบสองต่อเมื่อมันสั่ง tool แล้วปล่อย content ว่าง ซึ่งเป็นรอบที่ขอแค่ข้อความ ไม่เอา tool
    รอบสองอ่านผลจำลองของ tool ผิดบ่อย (เห็น accepted แล้วนึกว่าชาวบ้านส่งของมาแล้ว) จึงเลี่ยงไว้ก่อน
    """
    config = ai_config.get().communicator
    if config.provider != "typhoon":
        await psql.create_and_save_log(PROCESS, f"communicator ตั้ง provider {config.provider} ที่ยังไม่รองรับ รอบนี้เลยเงียบ")
        return None, [], config

    # protocol ต่อท้ายเสมอเพราะ prompt ในฐานอาจเก่ากว่าฟีเจอร์ tool calling
    messages = chatbot_session_to_messages(session)
    system = f"{config.prompt}\n\n{SET_FINISHED_PROTOCOL}" if config.prompt else SET_FINISHED_PROTOCOL
    messages = [{"role": "system", "content": system}, *messages]

    message = await typhoon.chat_with_tools(
        messages,
        COMMUNICATOR_TOOL_SCHEMAS,
        config.model_name,
        config.temperature,
        config.max_output_tokens,
    )
    if message is None:
        await psql.create_and_save_log(PROCESS, "ไม่มี provider ไหนตอบได้ รอบนี้เลยเงียบ")
        return None, [], config

    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        await psql.create_and_save_log(PROCESS, "communicator คืน tool_calls ในรูปที่อ่านไม่ออก")
        return None, [], config

    # มีข้อความมาแล้วก็ใช้เลย ไม่ว่าจะแนบ tool มาด้วยหรือไม่ — ข้อความคือของที่ชาวบ้านรอ
    # ทิ้งเมื่อไหร่ LINE เงียบทันที และเงียบแพงกว่าการไม่ได้ปักธงจบมาก
    # ไม่เรียก tool เลยคือเรื่องปกติของตาที่บทสนทนายังเดินอยู่ ไม่ต้อง log
    reply = message.get("content")
    if isinstance(reply, str) and reply.strip():
        return reply, tool_calls, config

    if not tool_calls:
        await psql.create_and_save_log(PROCESS, "communicator ไม่เรียก tool และไม่มีข้อความสำหรับตอบผู้ใช้")
        return None, [], config

    # เหลือทางเดียว: สั่ง tool มาแต่ไม่เขียนอะไรให้ชาวบ้าน ต้องยิงอีกรอบเอาเฉพาะข้อความ
    # id ตรวจตรงนี้เพราะใช้แค่ตอนปั้น message รอบนี้ สายที่จบในรอบแรกไม่ต้องมีก็ได้
    tool_messages = []
    for call in tool_calls:
        tool_call_id = call.get("id") if isinstance(call, dict) else None
        if not isinstance(tool_call_id, str) or not tool_call_id:
            await psql.create_and_save_log(PROCESS, "communicator คืน tool call ที่ไม่มี id")
            return None, [], config
        tool_messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": '{"accepted": true, "instruction": "Reply to the user now without another tool call."}',
        })

    assistant_message = {
        "role": "assistant",
        "content": message.get("content"),
        "tool_calls": tool_calls,
    }
    message = await typhoon.chat_with_tools(
        [*messages, assistant_message, *tool_messages],
        COMMUNICATOR_TOOL_SCHEMAS,
        config.model_name,
        config.temperature,
        config.max_output_tokens,
        tool_choice="none",
    )
    if message is None:
        await psql.create_and_save_log(PROCESS, "communicator ไม่ตอบหลังรับผล tool")
        return None, [], config

    # เรียก tool ซ้ำก็ช่างมัน ของที่ต้องการจากรอบนี้คือข้อความอย่างเดียว
    # ธงจบกับ quick reply ยึดของรอบแรกเสมอ ตัวซ้ำไม่ได้เห็นอะไรใหม่นอกจากผลจำลองที่เราป้อนเอง
    if message.get("tool_calls"):
        await psql.create_and_save_log(PROCESS, "communicator เรียก tool ซ้ำหลังได้รับผลแล้ว ใช้เฉพาะข้อความและยึด tool รอบแรก")

    reply = message.get("content")
    if not isinstance(reply, str) or not reply.strip():
        await psql.create_and_save_log(PROCESS, "communicator ไม่คืนข้อความสำหรับตอบผู้ใช้")
        return None, [], config

    return reply, tool_calls, config

def conversation_to_transcript (conversation: list[Turn]) -> str:
    """ปั้นบทสนทนาเป็นข้อความก้อนเดียวให้ analyzer อ่าน

    ไม่ส่งเป็น messages หลายตาแบบตอนคุย เพราะ analyzer ไม่ได้คุยต่อ มันอ่านของที่จบแล้ว
    ส่งเป็นบทสนทนาหลายตาเมื่อไหร่ โมเดลจะนึกว่าถึงตามันตอบชาวบ้าน แล้วเขียนคำถามออกมาแทนบทสรุป
    """
    name = {"user": "ชาวบ้าน", "assistant": "บอท"}
    return "\n".join(f"{name.get(turn.role, turn.role)}: {turn.content}" for turn in conversation)


async def analyzer (session_id: UUID) -> tuple[list[dict] | None, AgentConfig]:
    """อ่านบทสนทนาที่จบแล้วจากฐาน แล้วคืนรายการ tool ที่โมเดลสั่งให้ทำ

    ที่นี่ไม่ลงมือทำตามคำสั่งเอง แค่เอาคำสั่งมาส่งต่อ คนลงมือคือ ai_tools.run_tool_calls
    แยกกันเพราะการบันทึกลงฐานต้องเกิดใต้คนที่ถือ session อยู่ ไม่ใช่ใต้คนที่กำลังคุยกับ provider

    ค่าที่คืนมีสามความหมาย แต่มีแค่แบบเดียวที่แปลว่าใช้ได้:
    - None       = ไม่ได้คำตอบที่ใช้ได้ โมเดลไม่ตอบหรือตอบมาในรูปที่อ่านไม่ออก
    - []         = โมเดลตอบแล้วแต่ไม่ยอมเรียก tool ผิดกติกา คนเรียกต้องพาไปลองใหม่เหมือน None
    - มีสมาชิก   = โมเดลสั่งบันทึก เอาไปให้คนลงมือต่อ

    [] ไม่ได้แปลว่า "ไม่มีเรื่อง" — ไม่มีเรื่องมันต้องเรียก save_analyse ด้วย reports ว่าง
    ที่นี่ยังแยก None กับ [] ไว้เพราะสองอันนี้ต้อง log คนละแบบ คนอ่าน log จะได้รู้ว่าพังที่สายหรือที่ตัวโมเดล
    """
    config = ai_config.get().analyzer
    if config.provider != "typhoon":
        await psql.create_and_save_log(PROCESS, f"analyzer ตั้ง provider {config.provider} ที่ยังไม่รองรับ รอบนี้เลยข้าม")
        return None, config

    conversation = await psql.get_conversation(session_id)
    if not conversation:
        await psql.create_and_save_log(PROCESS, f"session {session_id} ไม่มีบทสนทนาในฐาน ไม่มีอะไรให้วิเคราะห์")
        return None, config

    # กติกาการเรียก tool ต่อท้ายเสมอ ไม่ว่า prompt จะมาจากแถว active ใน db หรือจาก default
    # db อาจถือ prompt เก่าที่เขียนไว้ก่อนมี tool calling อยู่ ถ้าไม่เติมให้ โมเดลจะไม่เรียก tool แล้วล้มทุก session
    # ต่อท้ายไม่ใช่แทนที่ ตัว prompt ยังคุมน้ำเสียงกับวิธีแยกเรื่องได้ตามเดิม
    system = f"{config.prompt}\n\n{SAVE_ANALYSE_PROTOCOL}" if config.prompt else SAVE_ANALYSE_PROTOCOL

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": conversation_to_transcript(conversation)},
    ]

    message = await typhoon.chat_with_tools(
        messages,
        [SAVE_ANALYSE_TOOL],
        config.model_name,
        config.temperature,
        config.max_output_tokens,
    )
    if message is None:
        await psql.create_and_save_log(PROCESS, f"session {session_id} วิเคราะห์ไม่สำเร็จ โมเดลไม่ตอบ")
        return None, config

    # ไม่สั่ง tool ช่องนี้หายไปเลยหรือมาเป็น null ทั้งสองแบบแปลว่า "ไม่มีอะไรให้บันทึก" เหมือนกัน
    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        await psql.create_and_save_log(PROCESS, f"session {session_id} โมเดลคืน tool_calls ในรูปที่อ่านไม่ออก {type(tool_calls).__name__}")
        return None, config

    # โมเดลดื้อตอบเป็นบทสรุปแทนการเรียก tool ก็มาลงตรงนี้ เก็บคำที่มันเขียนไว้ดูว่ามันเข้าใจงานผิดตรงไหน
    # ลิสต์ว่างไม่ได้แปลว่า "ไม่มีเรื่อง" อีกแล้ว — ไม่มีเรื่องมันต้องเรียก save_analyse ด้วย reports ว่าง
    # เงียบเฉย ๆ คือผิดกติกา คนเรียกจะพาไปลองใหม่
    if not tool_calls:
        await psql.create_and_save_log(
            PROCESS, f"session {session_id} โมเดลไม่เรียก tool เลย เขียนมาว่า {message.get('content')!r}"
        )

    return tool_calls, config
