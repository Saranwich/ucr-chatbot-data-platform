import json
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.clients import psql, redis, line as line_cli, storage, typhoon
from app.schemas.report import AiResponse, Image, Location, Message, Session
from app.schemas.turn import Turn
from app.schemas.user import User
from app.services import ai, ai_tools
from app.services.config import system_config

PROCESS = "services.chatbot"

# ลองวิเคราะห์ได้กี่ครั้งในการปิดหนึ่งรอบ ครบแล้วเลิกลอง ไม่ปล่อยให้ session เดียวกินเวลาตัวกวาดไม่จบ
# ไม่อยู่ใน default_value เพราะไม่ใช่ของที่แอดมินปรับระหว่างแอปรัน
ANALYSER_MAX_ATTEMPTS = 3


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

    # มีคนพิมพ์เข้ามาแปลว่ายังไม่จบ ถอนธงก่อนถามโมเดลทุกครั้ง ไม่ต้องรอให้มันถอนเอง
    # โมเดลถอนได้แค่ตอนถูกเรียก ถ้าตัวกวาดมาถึงก่อนข้อความถัดไปก็ปิดไปแล้ว สายเกิน
    # มันจะปักกลับเองในรอบนี้ถ้าอ่านว่าจบจริง หน้าที่มันเหลือแค่ยืนยัน ไม่ต้องจำของรอบก่อน
    await psql.set_session_finished(session_id, False)

    # add new turns to session
    session.extend(turns)
    await save_session_to_redis(redis_key, session_id, session)
    await psql.create_and_save_log(PROCESS,f"{user.id} ต่อ session {session_id} {len(turns)} ตา รวมเป็น {len(session)} ตา พร้อมส่งให้ LLM",)
    print("chatbot ปั้นของให้ LLM:", user.id, reply_token, session)

    # ขึ้นจุดสามจุดก่อนเข้าช่วงที่รอนานจริง คือตอนรอโมเดลเขียนคำตอบ
    await line_cli.start_loading(line_user_id)

    # send to ai
    reply, agent_config = await ai.communicator_reply(session)

    # verify ai response
    if reply is None:
        print("chatbot: ไม่มีคำตอบจากโมเดล ไม่มีข้อความตอบกลับ")
        return

    # เก็บคำตอบไว้ถาวรก่อน redis หมดอายุแล้วบทสนทนาฝั่งบอทจะหายไปทั้งดุ้น
    await psql.save_ai_response(AiResponse(
        session_id=session_id,
        agent=agent_config.agent,
        ai_config_id=agent_config.id,
        model_name=agent_config.model_name,
        content=reply.reply_text,
    ))

    # add ai response into session
    session.append(Turn(role="assistant", content_type="text", content=reply.reply_text))
    await save_session_to_redis(redis_key, session_id, session)

    # replie message to user via line pltform
    await line_cli.replie(
        reply_token,
        [reply.reply_text],
        quick_replies=[item.model_dump() for item in reply.quick_replies],
    )

    # ปักธงหลังตอบไลน์แล้ว ป้องกันตัวกวาดปิด session แทรกตอนที่คำตอบยังไม่ถึงชาวบ้าน
    # ไม่ต้องถอนธงตรงนี้ บรรทัดบนถอนให้ทุกตาที่มีข้อความเข้ามาอยู่แล้ว
    if reply.is_finished and not await psql.set_session_finished(session_id, True):
        await psql.create_and_save_log(PROCESS, f"ปักธงจบไม่สำเร็จ ไม่เจอ session {session_id} ในฐาน")
    print("ส่งข้อความกลับไปแล้ว")


async def open_session(user: User) -> UUID:
    """เปิดบทสนทนารอบใหม่ — เรียกตอน redis ไม่มีของค้าง แปลว่ารอบก่อนเงียบจนหมดอายุไปแล้ว"""
    session = Session(user_id=user.id)
    await psql.save_session(session)
    await psql.create_and_save_log(PROCESS, f"เปิด session {session.id} ให้ {user.id}")
    return session.id


async def is_session_finished(redis_key: str) -> bool:
    """บทสนทนารอบนี้ถูกปักธงว่าเล่าจบแล้วหรือยัง — ตัวกวาดถามก่อนตัดสินใจว่าจะรอเงียบต่อไหม

    ธงอยู่ในฐาน ไม่ได้อยู่ใน redis เพราะคนปักคือ handle_user_events ที่คุยกับฐานทางเดียว
    ต้องไปเอา session_id จาก redis ก่อน เพราะตัวกวาดถือแต่ชื่อ key
    """
    session_id, _ = await load_session_from_redis(redis_key)
    if session_id is None:
        return False

    session = await psql.get_session(session_id)
    return session is not None and session.is_finished


async def close_session(redis_key: str) -> int | None:
    """ปิดบทสนทนาหนึ่งรอบ ให้ analyzer อ่าน แล้วลงมือบันทึกตามที่มันสั่ง — เรียกจาก runtime ตอนใกล้หมดอายุ

    คืนจำนวนเรื่องที่บันทึกได้ หรือ None เมื่อวิเคราะห์ไม่สำเร็จ ตัวกวาดนับ "ปิดไปกี่ session" จาก None/ไม่ None
    ศูนย์เรื่องก็ยังนับว่าปิดแล้ว เพราะบทสนทนาที่ไม่มีเรื่องจริงก็ต้องจบ ไม่ใช่วนวิเคราะห์ใหม่ทุกรอบกวาด

    ลองได้ถึง ANALYSER_MAX_ATTEMPTS ครั้งในการเรียกครั้งเดียว ครบแล้วปักเป็น analysis_failed แล้วเลิกลองถาวร
    ไม่ปล่อยให้ตัวกวาดมาลองใหม่ทุกสองนาที เพราะรอบที่ล้มเพราะโมเดลกรอกค่าผิด รอไปก็ผิดเหมือนเดิม

    การลงมือทำตาม tool อยู่ที่นี่ ไม่ใช่ใน ai.py เพราะคนที่ถือ session อยู่คือคนนี้
    และไม่ใช่ใน runtime.py เพราะนั่นมีหน้าที่แค่หาว่า session ไหนถึงคิวปิด
    """
    session_id, turns = await load_session_from_redis(redis_key)
    if session_id is None:
        return None            # หมดอายุเองไปแล้วระหว่างทาง ไม่มีอะไรให้ปิด

    session = await psql.get_session(session_id)
    if session is None or session.status != "not_analyzed":
        print("close_session: ข้าม", session_id, "สถานะ", session.status if session else "ไม่มีในฐาน")
        return None

    # ชาวบ้านยังไม่ได้พูดสักคำ (ส่งสติกเกอร์มาอย่างเดียว หรือมีแต่ข้อความที่บอทยิงเข้าไป)
    # ไม่มีอะไรให้วิเคราะห์ ปิดทิ้งเลย ไม่ต้องจ่ายค่าเรียกโมเดลเพื่อให้มันตอบว่าไม่เจอเรื่อง
    if not any(turn.role == "user" for turn in turns):
        await psql.set_session_status(session_id, "analyzed")
        await redis.delete_session(redis_key)
        await psql.create_and_save_log(
            PROCESS, f"ปิด session {session_id} โดยไม่วิเคราะห์ เพราะชาวบ้านยังไม่ได้พูดอะไร"
        )
        print("close_session: ปิดแล้ว", session_id, "ไม่มีตาของชาวบ้าน ไม่เรียก analyzer")
        return 0

    await psql.set_session_status(session_id, "pending")

    # ลองใหม่ทั้งรอบ ไม่ใช่แค่ยิงซ้ำ เพราะรอบที่ล้มส่วนใหญ่ล้มที่โมเดลกรอกค่าผิด ไม่ใช่ที่สายขาด
    # ยิงคำสั่งเดิมซ้ำก็ได้ค่าผิดชุดเดิม ต้องให้มันอ่านบทสนทนาแล้วเขียนคำสั่งใหม่ทั้งอัน
    for attempt in range(1, ANALYSER_MAX_ATTEMPTS + 1):
        # None คือยังไม่ได้วิเคราะห์จริง ต่างจากลิสต์ว่างที่แปลว่าโมเดลตอบแล้วแต่ไม่ยอมเรียก tool
        # ลิสต์ว่างก็นับเป็นรอบที่ล้มเหมือนกัน เพราะกติกาคือต้องเรียก save_analyse เสมอ
        # ไม่มีเรื่องให้เก็บมันต้องบอกด้วยการส่ง reports ว่างมา ไม่ใช่ด้วยการเงียบ
        tool_calls, _ = await ai.analyzer(session_id)

        if tool_calls is not None:
            outcome = await ai_tools.run_tool_calls(session_id, tool_calls)
            if outcome.is_success:
                await psql.set_session_status(session_id, "analyzed")
                await redis.delete_session(redis_key)
                await psql.create_and_save_log(
                    PROCESS,
                    f"ปิด session {session_id} แล้ว บันทึกได้ {outcome.saved} เรื่อง ในครั้งที่ {attempt}",
                )
                print("close_session: ปิดแล้ว", session_id, "บันทึกได้", outcome.saved, "เรื่อง")
                return outcome.saved

            detail = f"สั่งมา {outcome.requested} เรื่อง เก็บได้ {outcome.saved} tool ที่ทำได้ {outcome.executed} ที่ล้ม {outcome.failed}"
        else:
            detail = "โมเดลไม่ตอบหรือตอบมาในรูปที่ใช้ไม่ได้"

        await psql.create_and_save_log(
            PROCESS, f"session {session_id} วิเคราะห์ครั้งที่ {attempt}/{ANALYSER_MAX_ATTEMPTS} ไม่สำเร็จ — {detail}"
        )
        print("close_session: วิเคราะห์ไม่สำเร็จ", session_id, "ครั้งที่", attempt, detail)

    # ครบโควตาแล้วยังไม่ได้เรื่อง — เลิกลองรอบนี้ และเลิกลองรอบหน้าด้วย
    # analyzed ไม่ได้เพราะไม่มีใครอ่านสำเร็จ not_analyzed ก็ไม่ได้เพราะจะปนกับของที่ยังไม่ถึงคิว
    # ต้องเป็นป้ายของตัวเอง คนมาตามเก็บทีหลังจะได้ query หาแถวที่ควรไปนั่งดูได้ตรง ๆ
    # แล้วลบ redis ทิ้ง ไม่งั้นตัวกวาดเจอ key เดิมทุกสองนาทีแล้วลองใหม่อีกสามครั้งไปเรื่อย ๆ จนหมดอายุ
    # บทสนทนายังอยู่ครบใน postgres ทั้ง messages และ ai_responses ตามเก็บทีหลังได้
    await psql.set_session_status(session_id, "analysis_failed")
    await redis.delete_session(redis_key)
    await psql.create_and_save_log(
        PROCESS,
        f"ANALYSIS_FAILED session {session_id} ลองครบ {ANALYSER_MAX_ATTEMPTS} ครั้งแล้วยังวิเคราะห์ไม่ได้ "
        f"เลิกลอง ปักสถานะ analysis_failed บทสนทนายังอยู่ในฐาน",
    )
    print("close_session: ANALYSIS_FAILED", session_id, "ลองครบ", ANALYSER_MAX_ATTEMPTS, "ครั้ง")
    return None


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
    """เก็บรูปไว้ แล้วส่งรหัสภายในให้โมเดลใช้ผูกกับ report

    รหัสนี้เป็นเพียงป้ายอ้างอิง โมเดลยังมองรูปไม่เห็นและต้องไม่บรรยายสิ่งที่อยู่ในรูป
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

    marker = f"[got image from user: image_id={image.id}]" if image_key else "[image download failed]"
    turn = Turn(role="user", content_type="image", content=marker)
    print("message_image_handler:", turn, image_key)
    return turn


async def message_location_handler(user: User, session_id: UUID, number: int, message: dict) -> Turn | None:
    """เก็บพิกัดไว้ แล้วบอกโมเดลด้วย id ภายใน ไม่ส่งตัวเลขพิกัดให้

    ตัวเลขพิกัดไม่มีความหมายกับโมเดล มันบอกไม่ได้ว่าตรงนั้นคือที่ไหน ส่งไปมีแต่จะหลอกให้มันเดาชื่อซอย
    id ทำให้ analyzer จับคู่พิกัดกับ report ได้ตรงแถว โค้ดจะตรวจซ้ำว่า id อยู่ใน session นี้จริง
    """
    try:
        location = Location(
            session_id=session_id,
            number=number,
            type="lat_lon",          # แชร์ผ่านไลน์ได้ตัวเลขมาเสมอ แบบ str ไว้รอเคสที่เขาพิมพ์บอกเอง
            lat=message.get("latitude"),
            lon=message.get("longitude"),
            address=message.get("address"),
        )
    except ValidationError as error:
        await psql.create_and_save_log(PROCESS, f"{user.id} ส่ง location ที่อ่านไม่ได้ {error}")
        return None
    await psql.save_location(location)

    turn = Turn(
        role="user",
        content_type="location",
        content=f"[got location from user: location_id={location.id}]",
    )
    print("message_location_handler:", turn, location.lat, location.lon)
    return turn

async def expiring_session_handler ():
    pass
    ## implement this function by get redis session and then call analyzer ai
