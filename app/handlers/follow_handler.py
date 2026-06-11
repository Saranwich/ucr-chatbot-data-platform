"""FollowEvent — ผู้ใช้ add เพื่อน (หรือ unblock กลับมา)

ทำสองอย่าง: upsert แถว User ทันที (เดิมแถวถูกสร้างตอนเริ่ม survey ครั้งแรกเท่านั้น)
แล้วทักทาย — คนยังไม่มี profile ได้ Flex ชวนไปกรอกใน Userdata LIFF
คน re-follow ที่กรอกแล้วได้คำต้อนรับเฉย ๆ ไม่ชวนซ้ำ
"""
from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3.messaging import ReplyMessageRequest, TextMessage

from app.config import WELCOME_TEXT, WELCOME_BACK_TEXT
from app.services.profile_messages import build_profile_invite
from app.services.survey_repository import get_or_create_user


async def handle_follow(event, line_bot_api, db: AsyncSession):
    user = await get_or_create_user(db, event.source.user_id)
    # อ่านธงก่อน commit — หลัง commit attribute จะ expired แล้วการแตะมันจะ
    # trigger lazy load แบบ sync ใน async session → MissingGreenlet
    has_profile = user.has_completed_profile
    await db.commit()

    invite = None if has_profile else build_profile_invite()
    if invite:
        messages = [TextMessage(text=WELCOME_TEXT), invite]
    elif has_profile:
        messages = [TextMessage(text=WELCOME_BACK_TEXT)]
    else:
        # ยังไม่มี LIFF_USERDATA_ID (dev) — ทักอย่างเดียว ปุ่มชวนกรอกยังสร้างไม่ได้
        messages = [TextMessage(text=WELCOME_TEXT)]

    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=event.reply_token, messages=messages)
    )
