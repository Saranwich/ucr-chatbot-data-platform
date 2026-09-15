from uuid import UUID

from app.clients import psql, typhoon
from app.schemas.ai_config import AgentConfig
from app.schemas.communicator import CommunicatorReply
from app.schemas.turn import Turn
from app.services.ai_tools import SAVE_ANALYSE_PROTOCOL, SAVE_ANALYSE_TOOL
from app.services.communicator_output import (
    COMMUNICATOR_OUTPUT_CONTRACT,
    RESPONSE_FORMAT,
    parse_communicator_reply,
    past_reply_as_json,
)
from app.services.config import ai_config

PROCESS = "services.ai"


def chatbot_session_to_messages (session: list[Turn]) -> list[dict]:
    """แปลงบทสนทนาของเราเป็นรูปที่ provider อ่านรู้เรื่อง

    Turn.role ใช้คำเดียวกับ OpenAI อยู่แล้ว (user / assistant / system)
    เลยยกมาตรง ๆ ส่วน content_type ไม่ได้ส่งไป โมเดลอ่านจาก content พอ

    ยกเว้นตาของบอท ที่ต้องเขียนกลับเป็น JSON ตามสัญญาก่อนส่ง ไม่ใช่ส่งข้อความเปล่าที่เก็บไว้
    เราเก็บแค่ reply_text ลงฐานเพราะนั่นคือของที่ชาวบ้านเห็น แต่โมเดลต้องเห็นรูปที่มันเคยคาย
    ไม่งั้นมันลอกรูปร้อยแก้วจากตาเก่าของตัวเอง แล้วเลิกคาย JSON ทั้งบทสนทนา (วัดแล้ว 4/24)
    """
    return [
        {
            "role": turn.role,
            "content": past_reply_as_json(turn.content) if turn.role == "assistant" else turn.content,
        }
        for turn in session
    ]


async def communicator_reply (session: list[Turn]) -> tuple[CommunicatorReply | None, AgentConfig]:
    """ถามโมเดลว่าจะตอบอะไร คืนคำตอบที่แกะแล้วให้ chatbot เอาไปส่งไลน์

    คืน config ที่ใช้ยิงรอบนั้นกลับไปด้วย คนเรียกจะได้เก็บลงฐานว่าคำตอบนี้ออกมาจากโมเดลตัวไหน

    ยิงรอบเดียวจบเสมอ เพราะสิ่งที่ communicator ต้องคายคือข้อความ ธงจบ และปุ่ม ซึ่งมันรู้ครบตั้งแต่ตาแรก
    ไม่มีอะไรจากข้างนอกให้รอ การยิงรอบสองจึงไม่เคยเพิ่มข้อมูลให้มันเลย มีแต่เพิ่มเวลากับโอกาสตอบมั่ว
    (ของเดิมป้อนผลจำลอง {"accepted": true} กลับเข้าไป แล้วมันอ่านว่าชาวบ้านส่งของมาจริง)

    ธงจบกับปุ่มยอมหายได้ ข้อความห้ามหาย — ตัวแกะใน communicator_output ถือกติกานั้นไว้ทั้งชุด
    """
    config = ai_config.get().communicator
    if config.provider != "typhoon":
        await psql.create_and_save_log(PROCESS, f"communicator ตั้ง provider {config.provider} ที่ยังไม่รองรับ รอบนี้เลยเงียบ")
        return None, config

    # สัญญาต่อท้ายเสมอเพราะ prompt ในฐานอาจเก่ากว่ารูปคำตอบที่โค้ดรออยู่
    system = f"{config.prompt}\n\n{COMMUNICATOR_OUTPUT_CONTRACT}" if config.prompt else COMMUNICATOR_OUTPUT_CONTRACT
    messages = [{"role": "system", "content": system}, *chatbot_session_to_messages(session)]

    raw = await typhoon.chat(
        messages,
        config.model_name,
        config.temperature,
        config.max_output_tokens,
        response_format=RESPONSE_FORMAT,
    )
    if raw is None:
        await psql.create_and_save_log(PROCESS, "ไม่มี provider ไหนตอบได้ รอบนี้เลยเงียบ")
        return None, config

    return await parse_communicator_reply(raw), config


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
