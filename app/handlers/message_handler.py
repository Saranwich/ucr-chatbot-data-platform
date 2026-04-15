from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    LocationAction,
    CameraAction
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import User, SurveySession
from app.utils.survey_loader import survey_manager
from app.services.survey_service import process_survey_answer, start_survey_session

SURVEY_TRIGGER_MAP = {
    "เริ่มทำแบบสำรวจ": "v1"
    # อนาคตถ้ามีโปรเจกต์ใหม่ แค่มาเพิ่มตรงนี้ เช่น "รายงานน้ำท่วม": "flood_v2"
}

async def handle_text_message(event, line_bot_api, db: AsyncSession):
    text = event.message.text.strip()
    
    # อ่านแล้วเข้าใจทันที: "ถ้าข้อความนี้อยู่ในแผนผังจุดชนวนแบบสำรวจ..."
    if text in SURVEY_TRIGGER_MAP:
        target_version = SURVEY_TRIGGER_MAP[text]
        await start_survey_session(event.source.user_id, target_version, event.reply_token, line_bot_api, db)
        return

    # ถ้าไม่ใช่ แปลว่าเป็นการตอบคำถามข้อความอิสระ
    await process_survey_answer(event.source.user_id, text, event.reply_token, line_bot_api, db)

async def handle_location_message(event, line_bot_api, db: AsyncSession):

    answer_data = {
        "lat": event.message.latitude, 
        "lng": event.message.longitude
    }
    # 2. โยนเข้าสมองกล (Service) ทันที
    await process_survey_answer(event.source.user_id, answer_data, event.reply_token, line_bot_api, db)

async def handle_image_message(event, line_bot_api, db: AsyncSession):
    # 1. แกะข้อมูลดิบ (LINE จะส่งเป็น message_id มาให้เราไปโหลดรูปอีกที)
    answer_data = {"image_id": event.message.id}
    # 2. โยนเข้าสมองกล
    await process_survey_answer(event.source.user_id, answer_data, event.reply_token, line_bot_api, db)
