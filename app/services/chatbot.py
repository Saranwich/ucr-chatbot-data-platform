import json

from app.clients import psql, redis, line as line_cli, typhoon
from app.schemas.turn import Turn
from app.services import ai

PROCESS = "services.chatbot"
SESSION_TTL = 60 * 60 #one hour


async def handle (req):
    handler_map = {
        "message": message_handler,
        "follow": follow_handler,
        "unfollow": unfollow_handler,
    }
    payload = await req.json()

    turns = []
    line_user_id = None
    reply_token = None

    for event in payload.get("events", []):
        event_type = event.get("type")
        handler = handler_map.get(event_type)

        #เจอ ประเภท event ที่ไม่มี handler รองรับ
        if handler is None:
            await psql.create_and_save_log(PROCESS, f"ยังไม่รับ event ชนิด {event_type}")
            continue

        turn = await handler(event)
        if turn is None:
            continue

        turns.append(turn)
        line_user_id = event.get("source", {}).get("userId")
        reply_token = event.get("replyToken") or reply_token

    if not turns:
        print("chatbot: ไม่มีตาไหนเข้า session รอบนี้")
        return

    # handler ต่อตาของรอบนี้เข้า redis ไปแล้ว อ่านกลับมาจะได้ของเก่าพ่วงของใหม่ครบก้อน
    session = await load_session_from_redis(f"session:{line_user_id}")

    await psql.create_and_save_log(
        PROCESS,
        f"{line_user_id} ต่อ session {len(turns)} ตา รวมเป็น {len(session)} ตา พร้อมส่งให้ LLM",
    )
    print("chatbot ปั้นของให้ LLM:", line_user_id, reply_token, session)

    resp = await ai.communicator_reply(session)
    if resp is None:
        print("chatbot: ไม่มีคำตอบจากโมเดล รอบนี้ไม่ตอบกลับ")
        return

    await append_to_session(line_user_id, Turn(role="assistant", content_type="text", content=resp))
    await line_cli.replie(reply_token, [resp])
    print("ส่งข้อความกลับไปแล้ว")


async def load_session_from_redis(redis_key: str) -> list[Turn]:
    """ขอบทสนทนาทั้งก้อนคืนมาเป็น Turn — ยังไม่เคยคุยกันก็ได้ลิสต์ว่าง"""
    raw = await redis.get_session(redis_key)
    if raw is None:
        return []
    return [Turn(**turn) for turn in json.loads(raw)]


async def save_session_to_redis(redis_key: str, session: list[Turn]) -> None:
    """เขียนทับบทสนทนาทั้งก้อน — ของเดิมใต้ key นั้นหายหมด"""
    raw = json.dumps([turn.model_dump() for turn in session], ensure_ascii=False)
    await redis.save_session(redis_key, raw, SESSION_TTL)


async def append_to_session(line_user_id: str, turn: Turn) -> None:
    redis_key = f"session:{line_user_id}"
    session = await load_session_from_redis(redis_key)
    session.append(turn)
    await save_session_to_redis(redis_key, session)
    await psql.create_and_save_log(
        PROCESS, f"\nต่อตา {turn.content_type} ของ {line_user_id} เข้า session"
    )


async def message_handler(event: dict) -> Turn | None:
    handler_map = {
        "text": message_text_handler,
        "image": message_image_handler,
        "location": message_location_handler,
    }

    line_user_id = event.get("source", {}).get("userId")
    if not line_user_id:
        await psql.create_and_save_log(PROCESS, "ข้อความไม่บอกว่าใครพิมพ์ ทิ้งไป")
        print("message_handler: ไม่รู้ว่าใครพิมพ์ ทิ้งไป")
        return None

    message = event.get("message", {})
    content_type = message.get("type")
    handler = handler_map.get(content_type)
    if handler is None:
        await psql.create_and_save_log(PROCESS, f"ยังไม่รับข้อความชนิด {content_type}")
        print("message_handler: ยังไม่รับข้อความชนิด", content_type)
        return None

    return await handler(line_user_id, message)


async def follow_handler(event: dict) -> Turn | None:
    line_user_id = event.get("source", {}).get("userId")
    if not line_user_id:
        return None

    turn = Turn(
        role="system",
        content_type="follow",
        content="ผู้ใช้เพิ่งเพิ่มเป็นเพื่อน ยังไม่ได้พูดอะไร",
    )
    await append_to_session(line_user_id, turn)
    print("follow_handler:", turn)
    return turn


async def unfollow_handler(event: dict) -> Turn | None:
    line_user_id = event.get("source", {}).get("userId")
    await psql.create_and_save_log(PROCESS, f"{line_user_id} เลิกติดตามแล้ว")
    print("unfollow_handler:", line_user_id, "เลิกติดตามแล้ว")
    return None


async def message_text_handler(line_user_id: str, message: dict) -> Turn:
    turn = Turn(
        role="user",
        content_type="text",
        content=message.get("text", ""),
    )
    await append_to_session(line_user_id, turn)
    print("message_text_handler:", turn)
    return turn


async def message_image_handler(line_user_id: str, message: dict) -> Turn:
    turn = Turn(
        role="user",
        content_type="image",
        content=message.get("id", ""),
    )
    await append_to_session(line_user_id, turn)
    print("message_image_handler:", turn)
    return turn


async def message_location_handler(line_user_id: str, message: dict) -> Turn:
    address = message.get("address") or "ไม่ได้บอกที่อยู่"
    turn = Turn(
        role="user",
        content_type="location",
        content=f"แชร์พิกัด {message.get('latitude')}, {message.get('longitude')} ({address})",
    )
    await append_to_session(line_user_id, turn)
    print("message_location_handler:", turn)
    return turn
