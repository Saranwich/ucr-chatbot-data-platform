import json
from uuid import UUID, uuid4

from app.clients import psql, redis, line as line_cli, storage, typhoon
from app.schemas.report import AiResponse, Image, Location, Message, Session
from app.schemas.turn import Turn
from app.schemas.user import User
from app.services import ai
from app.services.config import system_config

PROCESS = "services.chatbot"


async def handle (req):
    payload = await req.json()

    # LINE ยัด event ของทุกคนในแชนเนลมาก้อนเดียวได้ แยกตามเจ้าของก่อน ไม่ให้บทสนทนาปนกัน
    events_by_line_user: dict[str, list[dict]] = {}
    for event in payload.get("events", []):
        line_user_id = event.get("source", {}).get("userId")

        #ไม่รู้ว่า event นี้ของใคร ต่อ session ให้ใครไม่ได้
        if not line_user_id:
            await psql.create_and_save_log(PROCESS, f"event {event.get('type')} ไม่บอกว่าใคร ทิ้งไป")
            print("chatbot: ไม่รู้ว่า event นี้ของใคร ทิ้งไป")
            continue

        events_by_line_user.setdefault(line_user_id, []).append(event)

    for line_user_id, events in events_by_line_user.items():
        await handle_user_events(line_user_id, events)


async def handle_user_events(line_user_id: str, events: list[dict]) -> None:
    """คุยกับคนเดียว — หลาย event ของคนเดียวกันนับเป็นตาที่ต่อกันใน session เดียว"""
    handler_map = {
        "message": message_handler,
        "follow": follow_handler,
        "unfollow": unfollow_handler,
    }

    user = await get_or_create_user(line_user_id)

    # redis เป็นตัวบอกว่ารอบไหนยังคุยอยู่ — key หายไปเมื่อไหร่คือรอบนั้นจบแล้ว เปิดรอบใหม่
    redis_key = f"session:{user.id}"
    session_id, session = await load_session_from_redis(redis_key)
    if session_id is None:
        session_id = await open_session(user)

    # ข้อความถัดไปเป็นข้อที่เท่าไหร่ นับจากที่ผู้ใช้พูดไปแล้วในรอบนี้ ไม่นับตาของบอท
    number = sum(1 for turn in session if turn.role == "user") + 1

    turns = []
    reply_token = None

    for event in events:
        event_type = event.get("type")
        handler = handler_map.get(event_type)

        #เจอ ประเภท event ที่ไม่มี handler รองรับ
        if handler is None:
            await psql.create_and_save_log(PROCESS, f"ยังไม่รับ event ชนิด {event_type}")
            continue

        turn = await handler(user, session_id, number, event)
        if turn is None:
            continue

        # เก็บข้อความที่ผู้ใช้ส่งมาไว้ถาวร ตัว turn ที่โมเดลเห็นกับแถวในฐานเป็นข้อความเดียวกัน
        await psql.save_message(Message(session_id=session_id, number=number, content=turn.content))
        number += 1

        turns.append(turn)
        reply_token = event.get("replyToken") or reply_token #use last reply token to replie

    if not turns:
        print("chatbot: ไม่มีตาไหนเข้า session รอบนี้ ของ", user.id)
        return

    # add new turns to session
    session.extend(turns)
    await save_session_to_redis(redis_key, session_id, session)
    await psql.create_and_save_log(PROCESS,f"{user.id} ต่อ session {session_id} {len(turns)} ตา รวมเป็น {len(session)} ตา พร้อมส่งให้ LLM",)
    print("chatbot ปั้นของให้ LLM:", user.id, reply_token, session)

    # send to ai
    resp, agent_config = await ai.communicator_reply(session)

    # verify ai response
    if resp is None:
        print("chatbot: ไม่มีคำตอบจากโมเดล ไม่มีข้อความตอบกลับ")
        return

    # เก็บคำตอบไว้ถาวรก่อน redis หมดอายุแล้วบทสนทนาฝั่งบอทจะหายไปทั้งดุ้น
    await psql.save_ai_response(AiResponse(
        session_id=session_id,
        agent=agent_config.agent,
        ai_config_id=agent_config.id,
        model_name=agent_config.model_name,
        content=resp,
    ))

    # add ai response into session
    session.append(Turn(role="assistant", content_type="text", content=resp))
    await save_session_to_redis(redis_key, session_id, session)

    # replie message to user via line pltform
    await line_cli.replie(reply_token, [resp])
    print("ส่งข้อความกลับไปแล้ว")


async def open_session(user: User) -> UUID:
    """เปิดบทสนทนารอบใหม่ — เรียกตอน redis ไม่มีของค้าง แปลว่ารอบก่อนเงียบจนหมดอายุไปแล้ว"""
    session = Session(user_id=user.id)
    await psql.save_session(session)
    await psql.create_and_save_log(PROCESS, f"เปิด session {session.id} ให้ {user.id}")
    return session.id


async def close_session(redis_key: str) -> str | None:
    """ปิดบทสนทนาหนึ่งรอบแล้วส่งให้ analyzer อ่าน — เรียกจาก runtime ตอนใกล้หมดอายุ"""
    session_id, _ = await load_session_from_redis(redis_key)
    if session_id is None:
        return None            # หมดอายุเองไปแล้วระหว่างทาง ไม่มีอะไรให้ปิด

    session = await psql.get_session(session_id)
    if session is None or session.status != "not_analyzed":
        print("close_session: ข้าม", session_id, "สถานะ", session.status if session else "ไม่มีในฐาน")
        return None

    await psql.set_session_status(session_id, "pending")

    result, _ = await ai.analyzer(session_id)
    if result is None:
        # คืนสถานะ ไม่งั้นมันค้างเป็น pending แล้วรอบกวาดถัดไปจะข้ามตลอดไป
        await psql.set_session_status(session_id, "not_analyzed")
        print("close_session: วิเคราะห์ไม่สำเร็จ คืนของ ยังไม่ปิด", session_id)
        return None

    await psql.set_session_status(session_id, "analyzed")
    await redis.delete_session(redis_key)
    await psql.create_and_save_log(PROCESS, f"ปิด session {session_id} แล้ว")

    # รอบนี้ยังไม่มีที่เก็บผลวิเคราะห์ ลง log ไว้ก่อนให้เห็นว่า analyzer อ่านออกมาได้อะไร
    await psql.create_and_save_log(PROCESS, f"ผลวิเคราะห์ session {session_id}: {result}")
    print("close_session: ผลวิเคราะห์", session_id, "\n" + result)
    return result


async def get_or_create_user(line_user_id: str) -> User:
    """หา user จาก LINE id — ยังไม่เคยมีในแอปก็สร้างใหม่แล้วบันทึกเลย"""
    user = await psql.get_user_by_line_user_id(line_user_id)
    if user is None:
        user = User(id=uuid4(), line_user_id=line_user_id)
        await psql.save_user(user)
        await psql.create_and_save_log(PROCESS, f"user ใหม่ {user.id} จาก LINE {line_user_id}")
    return user


async def load_session_from_redis(redis_key: str) -> tuple[UUID | None, list[Turn]]:
    """ขอรอบที่คุยค้างอยู่คืนมา — ไม่มีของค้างก็ได้ (None, ลิสต์ว่าง) แปลว่าต้องเปิดรอบใหม่"""
    raw = await redis.get_session(redis_key)
    if raw is None:
        return None, []
    data = json.loads(raw)
    return UUID(data["session_id"]), [Turn(**turn) for turn in data["turns"]]


async def save_session_to_redis(redis_key: str, session_id: UUID, session: list[Turn]) -> None:
    """เขียนทับรอบที่คุยค้างทั้งก้อน — ของเดิมใต้ key นั้นหายหมด อายุเริ่มนับใหม่ทุกครั้ง"""
    raw = json.dumps(
        {"session_id": str(session_id), "turns": [turn.model_dump() for turn in session]},
        ensure_ascii=False,
    )
    await redis.save_session(redis_key, raw, system_config.get().session_ttl_seconds)


async def message_handler(user: User, session_id: UUID, number: int, event: dict) -> Turn | None:
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

    return await handler(user, session_id, number, message)


async def follow_handler(user: User, session_id: UUID, number: int, event: dict) -> Turn | None:
    # ยังไม่ได้ออกแบบว่าคนมาครั้งแรกต้องทำอะไร เลยไม่เปิด session จากตรงนี้
    await psql.create_and_save_log(PROCESS, f"{user.id} เพิ่มเป็นเพื่อนแล้ว")
    print("follow_handler:", user.id, "เพิ่มเป็นเพื่อนแล้ว")
    return None


async def unfollow_handler(user: User, session_id: UUID, number: int, event: dict) -> Turn | None:
    await psql.create_and_save_log(PROCESS, f"{user.id} เลิกติดตามแล้ว")
    print("unfollow_handler:", user.id, "เลิกติดตามแล้ว")
    return None


async def message_text_handler(user: User, session_id: UUID, number: int, message: dict) -> Turn:
    turn = Turn(
        role="user",
        content_type="text",
        content=message.get("text", ""),
    )
    print("message_text_handler:", turn)
    return turn


async def message_image_handler(user: User, session_id: UUID, number: int, message: dict) -> Turn:
    """เก็บรูปไว้ แล้วบอกโมเดลแค่ว่ามีรูปเข้ามา ไม่ส่งรหัสรูปให้

    โมเดลมองรูปไม่เห็นอยู่แล้ว รหัสรูปเลยไม่มีประโยชน์กับมัน มีแต่จะหลอกให้มันพูดถึงรูป
    ตัวรูปเก็บไว้ให้ ai ที่อ่านภาพมาอ่านทีหลัง
    โหลดไฟล์ไม่สำเร็จก็ยังเก็บแถวไว้ เพราะ line_image_url ยังพาไปตามเก็บใหม่ได้
    """
    message_id = message.get("id", "")
    line_image_url, data, content_type = await line_cli.get_image_content(message_id)

    image_key = None
    if data is None:
        await psql.create_and_save_log(PROCESS, f"{user.id} ส่งรูป {message_id} มา แต่โหลดไฟล์ไม่สำเร็จ")
    else:
        image_key = storage.save_image(data, content_type)

    image = Image(
        session_id=session_id,
        number=number,
        line_image_url=line_image_url,
        image_key=image_key,
        desc=None,
    )
    await psql.save_image(image)

    turn = Turn(
        role="user",
        content_type="image",
        content="[got image from user]",
    )
    print("message_image_handler:", turn, image_key)
    return turn


async def message_location_handler(user: User, session_id: UUID, number: int, message: dict) -> Turn:
    """เก็บพิกัดไว้ แล้วบอกโมเดลแค่ว่ามีพิกัดเข้ามา ไม่ส่งตัวเลขให้

    ตัวเลขพิกัดไม่มีความหมายกับโมเดล มันบอกไม่ได้ว่าตรงนั้นคือที่ไหน ส่งไปมีแต่จะหลอกให้มันเดาชื่อซอย
    ตัวพิกัดเก็บไว้ให้ analyzer เอาไปปักหมุดทีหลัง
    """
    location = Location(
        session_id=session_id,
        number=number,
        type="lat_lon",          # แชร์ผ่านไลน์ได้ตัวเลขมาเสมอ แบบ str ไว้รอเคสที่เขาพิมพ์บอกเอง
        lat=message.get("latitude"),
        lon=message.get("longitude"),
        address=message.get("address"),
    )
    await psql.save_location(location)

    turn = Turn(
        role="user",
        content_type="location",
        content="[got location from user]",
    )
    print("message_location_handler:", turn, location.lat, location.lon)
    return turn

async def expiring_session_handler ():
    pass
    ## implement this function by get redis session and then call analyzer ai