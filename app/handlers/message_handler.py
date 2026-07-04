from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3.webhooks import TextMessageContent
from linebot.v3.messaging import ReplyMessageRequest, TextMessage
from app.services.ai_tool import build_question
from app.handlers.info_handler import handle_info_request
from app.handlers.stat_handler import handle_stat_request
from app.handlers.report_handler import handle_report_request
from app.handlers.manual_handler import handle_manual_request
from app.handlers.broadcast_flow_handler import (
    get_active_report, continue_flow, start_report, decline, YES_MAP, NO_MAP,
)


async def route_message_event(event, line_bot_api, db: AsyncSession):
    """Single router for a MessageEvent: dispatch by content type."""
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
    """Main Router for incoming text messages."""
    text = event.message.text.strip()

    # 1. Route to Info Handler
    if text == "ข้อมูลโครงการ":
        await handle_info_request(event, line_bot_api)
        return

    # 2. Route to Stat Handler
    if text == "สรุปผล":
        await handle_stat_request(event, line_bot_api)
        return

    # 3. Route to Report Handler (Fallback for 'รายงานปัญหา' text)
    if text == "รายงานปัญหา":
        await handle_report_request(event, line_bot_api)
        return

    # 4. Route to Manual Handler
    if text == "คู่มือการใช้งาน":
        await handle_manual_request(event, line_bot_api)
        return

    # 5. Weather broadcast — ปุ่มยืนยัน (เริ่มเก็บข้อมูล) / ปฏิเสธ
    #    (ตรงนี้ยังไม่มี active report เพราะเพิ่งกดปุ่มแรกจาก broadcast → พอสร้าง report แล้ว
    #     message ถัดๆ ไปจะโดน active-check ใน route_message_event ดักไป continue_flow เอง)
    if text in YES_MAP:
        await start_report(event, line_bot_api, db, YES_MAP[text])
        return
    if text in NO_MAP:
        await decline(event, line_bot_api, db, NO_MAP[text])
        return

    # 6. Free text → AI core (step 1: hardcoded reply; Gemini + memory come later)
    answer = await build_question(text)
    await line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=answer)])
    )
