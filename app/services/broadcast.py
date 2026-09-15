import asyncio
from uuid import UUID

import httpx

from app.clients import line, psql
from app.schemas.broadcast import BroadcastCreate
from app.schemas.turn import Turn
from app.services import chatbot

_running: set[asyncio.Task] = set()


async def send(
    text: str, audience: str, user_ids: list[UUID] | None = None, force_send: bool = False
) -> dict:
    """ส่งข้อความหาชาวบ้านตามกลุ่มที่เลือก คืนข้อมูลฉบับนั้นทันทีโดยไม่รอยิงครบ

    ตรึงรายชื่อผู้รับลงฐานก่อนยิงเสมอ ล้มกลางทางจะได้รู้ว่าค้างที่ใคร
    การยิงจริงวิ่งต่อเบื้องหลัง คนเรียกจึงตอบ HTTP ได้ทันทีโดยไม่ต้องรอ 500 คน
    """
    payload = BroadcastCreate(text=text, audience=audience, user_ids=user_ids or [])
    broadcast_id = await psql.save_broadcast(payload.text, payload.audience, payload.user_ids)
    task = asyncio.create_task(dispatch(broadcast_id, force_send))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return await psql.get_broadcast(broadcast_id)


async def dispatch(broadcast_id: UUID, force_send: bool = False) -> None:
    """ยิงทีละคนจนหมดคิว ยิงไม่สำเร็จก็เดินต่อ ไม่ให้คนเดียวค้างทั้งฉบับ

    คนที่พูดกับบอทไปแล้วในรอบที่ยังไม่ปิดถือว่ากำลังคุยอยู่ ปักเป็น skipped ไม่ยิงหา
    ข้อความประกาศจะได้ไม่แทรกกลางบทสนทนา — เปิดรอบไว้แต่ยังไม่พูดไม่นับ ยังยิงได้ตามปกติ

    force_send ยิงทับคนที่กำลังคุยอยู่ แล้วต่อข้อความเข้ารอบนั้นเลย
    บอทจะได้เห็นว่าตัวเองพูดอะไรไปตอนชาวบ้านตอบกลับ

    ยิงแล้วไม่รู้ผล (เน็ตหลุด หมดเวลา) ปักเป็น unknown ไม่หยิบมายิงซ้ำเอง
    เพราะไลน์อาจส่งถึงชาวบ้านไปแล้ว ยิงซ้ำ = เขาได้ข้อความสองรอบ
    """
    broadcast = await psql.get_broadcast(broadcast_id)
    if broadcast is None or broadcast["status"] != "sending":
        return
    while delivery := await psql.claim_broadcast_recipient(broadcast_id):
        redis_key = f"session:{delivery['user_id']}"
        session_id, turns = await chatbot.load_session_from_redis(redis_key)
        is_talking = any(turn.role == "user" for turn in turns)
        if is_talking and not force_send:
            await psql.finish_broadcast_recipient(delivery["id"], "skipped")
            continue
        try:
            response_status = await line.push(
                delivery["line_user_id"], [broadcast["text"]], delivery["retry_key"]
            )
        except (httpx.TimeoutException, httpx.TransportError) as error:
            await psql.finish_broadcast_recipient(
                delivery["id"], "unknown", error=type(error).__name__
            )
        except Exception as error:
            await psql.finish_broadcast_recipient(
                delivery["id"], "unknown", error=type(error).__name__
            )
        else:
            status = "sent" if response_status == 200 else "failed"
            if status == "sent" and session_id is not None:
                await chatbot.save_session_to_redis(
                    redis_key,
                    session_id,
                    turns + [Turn(role="assistant", content_type="text", content=broadcast["text"])],
                )
            await psql.finish_broadcast_recipient(
                delivery["id"], status, response_status=response_status
            )
    await psql.complete_broadcast(broadcast_id)
