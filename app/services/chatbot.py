import json
from uuid import uuid4

from app.clients import psql, redis, line as line_cli, typhoon
from app.schemas.turn import Turn
from app.schemas.user import User
from app.services import ai, system_setting

PROCESS = "services.chatbot"


async def handle (req):
    handler_map = {
        "message": message_handler,
        "follow": follow_handler,
        "unfollow": unfollow_handler,
    }
    payload = await req.json()

    turns = []
    user = None
    reply_token = None

    for event in payload.get("events", []):
        event_type = event.get("type")
        handler = handler_map.get(event_type)

        #เจอ ประเภท event ที่ไม่มี handler รองรับ
        if handler is None:
            await psql.create_and_save_log(PROCESS, f"ยังไม่รับ event ชนิด {event_type}")
            continue

        line_user_id = event.get("source", {}).get("userId")
        if not line_user_id:
            await psql.create_and_save_log(PROCESS, f"event {event_type} ไม่บอกว่าใคร ทิ้งไป")
            print("chatbot: ไม่รู้ว่า event นี้ของใคร ทิ้งไป")
            continue

        user = await get_or_create_user(line_user_id)
        turn = await handler(user, event)
        if turn is None:
            continue

        turns.append(turn)
        reply_token = event.get("replyToken") or reply_token #use last reply token to replie

    if not turns:
        print("chatbot: ไม่มีตาไหนเข้า session รอบนี้")
        return

    # get session in redis
    redis_key = f"session:{user.id}"
    session = await load_session_from_redis(redis_key)

    # add new turns to session
    session.extend(turns)
    await save_session_to_redis(redis_key, session)
    await psql.create_and_save_log(PROCESS,f"{user.id} ต่อ session {len(turns)} ตา รวมเป็น {len(session)} ตา พร้อมส่งให้ LLM",)
    print("chatbot ปั้นของให้ LLM:", user.id, reply_token, session)

    # send to ai
    resp = await ai.communicator_reply(session)

    # verify ai response
    if resp is None:
        print("chatbot: ไม่มีคำตอบจากโมเดล ไม่มีข้อความตอบกลับ")
        return

    # add ai response into session
    session.append(Turn(role="assistant", content_type="text", content=resp))
    await save_session_to_redis(redis_key, session)

    # replie message to user via line pltform
    await line_cli.replie(reply_token, [resp])
    print("ส่งข้อความกลับไปแล้ว")


async def get_or_create_user(line_user_id: str) -> User:
    """หา user จาก LINE id — ยังไม่เคยมีในแอปก็สร้างใหม่แล้วบันทึกเลย"""
    user = await psql.get_user_by_line_user_id(line_user_id)
    if user is None:
        user = User(id=uuid4(), line_user_id=line_user_id)
        await psql.save_user(user)
        await psql.create_and_save_log(PROCESS, f"user ใหม่ {user.id} จาก LINE {line_user_id}")
    return user


async def load_session_from_redis(redis_key: str) -> list[Turn]:
    """ขอบทสนทนาทั้งก้อนคืนมาเป็น Turn — ยังไม่เคยคุยกันก็ได้ลิสต์ว่าง"""
    raw = await redis.get_session(redis_key)
    if raw is None:
        return []
    return [Turn(**turn) for turn in json.loads(raw)]


async def save_session_to_redis(redis_key: str, session: list[Turn]) -> None:
    """เขียนทับบทสนทนาทั้งก้อน — ของเดิมใต้ key นั้นหายหมด"""
    raw = json.dumps([turn.model_dump() for turn in session], ensure_ascii=False)
    await redis.save_session(redis_key, raw, system_setting.get().session_ttl_seconds)


async def message_handler(user: User, event: dict) -> Turn | None:
    handler_map = {
        "text": message_text_handler,
        "image": message_image_handler,
        "location": message_location_handler,
    }

    message = event.get("message", {})
    content_type = message.get("type")
    handler = handler_map.get(content_type)
    if handler is None:
        await psql.create_and_save_log(PROCESS, f"ยังไม่รับข้อความชนิด {content_type}")
        print("message_handler: ยังไม่รับข้อความชนิด", content_type)
        return None

    return await handler(user, message)


async def follow_handler(user: User, event: dict) -> Turn | None:
    # ยังไม่ได้ออกแบบว่าคนมาครั้งแรกต้องทำอะไร เลยไม่เปิด session จากตรงนี้
    await psql.create_and_save_log(PROCESS, f"{user.id} เพิ่มเป็นเพื่อนแล้ว")
    print("follow_handler:", user.id, "เพิ่มเป็นเพื่อนแล้ว")
    return None


async def unfollow_handler(user: User, event: dict) -> Turn | None:
    await psql.create_and_save_log(PROCESS, f"{user.id} เลิกติดตามแล้ว")
    print("unfollow_handler:", user.id, "เลิกติดตามแล้ว")
    return None


async def message_text_handler(user: User, message: dict) -> Turn:
    turn = Turn(
        role="user",
        content_type="text",
        content=message.get("text", ""),
    )
    print("message_text_handler:", turn)
    return turn


async def message_image_handler(user: User, message: dict) -> Turn:
    turn = Turn(
        role="user",
        content_type="image",
        content=message.get("id", ""),
    )
    print("message_image_handler:", turn)
    return turn


async def message_location_handler(user: User, message: dict) -> Turn:
    address = message.get("address") or "ไม่ได้บอกที่อยู่"
    turn = Turn(
        role="user",
        content_type="location",
        content=f"แชร์พิกัด {message.get('latitude')}, {message.get('longitude')} ({address})",
    )
    print("message_location_handler:", turn)
    return turn
