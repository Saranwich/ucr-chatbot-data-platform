"""FollowEvent — ผู้ใช้ add เพื่อน (หรือ unblock กลับมา)

upsert แถว User ทันที แล้วทักทาย. คน re-follow ที่กรอก profile แล้วได้คำต้อนรับกลับ
คนใหม่ได้คำทักทายเริ่มต้น (V2: ไม่ชวนกรอก profile แล้ว — ทำผ่าน Userdata LIFF อย่างเดียว)
"""
from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3.messaging import ReplyMessageRequest, TextMessage

from app.config import WELCOME_TEXT, WELCOME_BACK_TEXT
from app.services.user import get_or_create_user


async def handle_follow(event, line_bot_api, db: AsyncSession):
    user = await get_or_create_user(db, event.source.user_id)
    # อ่านธงก่อน commit — หลัง commit attribute จะ expired แล้วการแตะมันจะ
    # trigger lazy load แบบ sync ใน async session → MissingGreenlet
    has_profile = user.has_completed_profile
    await db.commit()

    text = WELCOME_BACK_TEXT if has_profile else WELCOME_TEXT
    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=text)])
    )
