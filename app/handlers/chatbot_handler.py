from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3.messaging import Configuration, AsyncApiClient, AsyncMessagingApiBlob

from app.services.survey_service import start_survey_session, process_survey_answer
from app.config import SURVEY_TRIGGER_MAP, CHANNEL_ACCESS_TOKEN
from app.utils import storage

async def handle_chatbot_chat(event, line_bot_api, db: AsyncSession, text: str):
    """Handles the Chatbot-based survey/chat flow."""
    # Check if the text is a trigger to start a new survey
    if text in SURVEY_TRIGGER_MAP:
        target_version = SURVEY_TRIGGER_MAP[text]
        await start_survey_session(event.source.user_id, target_version, event.reply_token, line_bot_api, db)
        return True
    
    # Otherwise, it might be an answer to an ongoing survey
    await process_survey_answer(event.source.user_id, text, event.reply_token, line_bot_api, db)
    return True

async def handle_chatbot_location(event, line_bot_api, db: AsyncSession):
    """Handles incoming location messages for the chatbot."""
    answer_data = {
        "lat": event.message.latitude, 
        "lng": event.message.longitude
    }
    await process_survey_answer(event.source.user_id, answer_data, event.reply_token, line_bot_api, db)

async def _persist_line_image(image_id: str):
    """ดึง bytes จาก LINE CDN มาเก็บถาวรทันที (CDN ลบรูปทิ้งหลังผ่านไปสักพัก)

    คืน storage key หรือ None เมื่อพลาด — การเก็บรูปต้องไม่ทำให้ flow การตอบพัง:
    ยังมี image_id ให้ proxy สดได้จนกว่า CDN จะหมดอายุ
    """
    try:
        configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
        async with AsyncApiClient(configuration) as api_client:
            blob_api = AsyncMessagingApiBlob(api_client)
            content = await blob_api.get_message_content(image_id)
        return storage.save_image(f"survey/{image_id}.jpg", content)
    except Exception as e:
        print(f"⚠️ persist survey image {image_id} failed: {e}")
        return None


async def handle_chatbot_image(event, line_bot_api, db: AsyncSession):
    """Handles incoming image messages for the chatbot."""
    answer_data = {"image_id": event.message.id}
    storage_key = await _persist_line_image(event.message.id)
    if storage_key:
        answer_data["storage_key"] = storage_key
    await process_survey_answer(event.source.user_id, answer_data, event.reply_token, line_bot_api, db)
