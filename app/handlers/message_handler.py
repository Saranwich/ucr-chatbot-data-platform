from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3.webhooks import TextMessageContent

from app.config import PROJECT_INFO_TEXT, SUMMARY_PLACEHOLDER_TEXT, REPORT_DEVELOPMENT_TEXT
from app.services import line as line_service
from app.services import session
from app.services.ai_tool import build_question, build_broadcast_reply
from app.services.user import get_or_create_user
from app.handlers.broadcast_flow_handler import (
    get_active_report, continue_flow, decline, YES_MAP, NO_MAP,
)

# ปุ่ม rich menu ที่ตอบด้วยข้อความคงที่ (คู่มือเป็น Flex แยกไว้ด้านล่าง)
RICH_MENU_REPLIES = {
    "ข้อมูลโครงการ": PROJECT_INFO_TEXT,
    "สรุปผล": SUMMARY_PLACEHOLDER_TEXT,
    "รายงานปัญหา": REPORT_DEVELOPMENT_TEXT,
}


async def route_message_event(event, line_bot_api, db: AsyncSession):
    """Single router for a MessageEvent: dispatch by content type."""
    # ★ กันแถว users ให้มีก่อนเสมอ: คนที่เพิ่มเพื่อนก่อน deploy/ก่อน DB นี้จะไม่มี
    #   FollowEvent → ไม่มีแถว users แต่ conversations/reports FK ชี้มาที่ users
    #   (commit ทันทีเพื่อให้ session แยกของ AI flow มองเห็นแถวนี้)
    await get_or_create_user(db, event.source.user_id)
    await db.commit()
    # ★ ถ้า user กำลังกรอก broadcast report ค้างอยู่ → route ทุก message (text/location/image)
    #   เข้า flow ก่อน (บอทดู status ว่ารอ note/location/photo อยู่ แล้วจัดการให้ถูก)
    active = await get_active_report(db, event.source.user_id)
    if active:
        await continue_flow(event, line_bot_api, db, active)
        return

    if isinstance(event.message, TextMessageContent):
        await handle_text_message(event, line_bot_api, db)
    # ponytail: non-broadcast location/image ไม่มีปลายทางจนกว่า AI flow (step 1, #88)
    #           จะต่อ services/ai_tool เข้ามารับ — ตอนนี้ปล่อยผ่าน


async def handle_text_message(event, line_bot_api, db: AsyncSession):
    """Route incoming text: rich-menu buttons, broadcast confirm/decline, else AI."""
    text = event.message.text.strip()

    # 1. Rich-menu static replies
    if text in RICH_MENU_REPLIES:
        await line_service.reply_text(line_bot_api, event.reply_token, RICH_MENU_REPLIES[text])
        return
    if text == "คู่มือการใช้งาน":
        await line_service.reply_messages(line_bot_api, event.reply_token, line_service.build_manual_messages())
        return

    # 2. Weather broadcast — ปุ่มยืนยัน → AI คุยเก็บรายละเอียด (แทน state machine เดิม)
    #    mode flag ใน Redis คือ "ความจำ" ว่า session นี้คุยต่อจาก alert ไหน
    if text in YES_MAP:
        alert_type = YES_MAP[text]
        await session.set_broadcast_mode(event.source.user_id, alert_type)
        answer = await build_broadcast_reply(event.source.user_id, text, alert_type)
        await line_service.reply_text(line_bot_api, event.reply_token, answer)
        return
    if text in NO_MAP:
        await decline(event, line_bot_api, db, NO_MAP[text])
        return

    # 3. Free text → AI core (Gemini + Redis conversation memory)
    #    ถ้าค้างโหมด broadcast อยู่ → คุยด้วย prompt broadcast จนกว่าจะบันทึกเสร็จ/หมดเวลา
    alert_type = await session.get_broadcast_mode(event.source.user_id)
    if alert_type:
        answer = await build_broadcast_reply(event.source.user_id, text, alert_type)
    else:
        answer = await build_question(event.source.user_id, text)
    await line_service.reply_text(line_bot_api, event.reply_token, answer)
