"""FollowEvent — ผู้ใช้ add เพื่อน (หรือ unblock กลับมา)

upsert แถว User ทันที แล้วทักทาย. คน re-follow ที่กรอก profile แล้วได้คำต้อนรับกลับ
คนใหม่ได้คำทักทายเริ่มต้น (V2: ไม่ชวนกรอก profile แล้ว — ทำผ่าน Userdata LIFF อย่างเดียว)
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import WELCOME_TEXT, WELCOME_BACK_TEXT
from app.services.user import get_or_create_user
from app.services import line as line_service


async def handle_follow(event, line_bot_api, db: AsyncSession):
    user = await get_or_create_user(db, event.source.user_id)
    # อ่านธงก่อน commit — หลัง commit attribute จะ expired แล้วการแตะมันจะ
    # trigger lazy load แบบ sync ใน async session → MissingGreenlet
    has_profile = user.has_completed_profile
    await db.commit()

    text = WELCOME_BACK_TEXT if has_profile else WELCOME_TEXT
    await line_service.reply_text(line_bot_api, event.reply_token, text)
