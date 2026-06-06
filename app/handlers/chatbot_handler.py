from sqlalchemy.ext.asyncio import AsyncSession
from app.services.survey_service import start_survey_session, process_survey_answer
from app.config import SURVEY_TRIGGER_MAP

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

async def handle_chatbot_image(event, line_bot_api, db: AsyncSession):
    """Handles incoming image messages for the chatbot."""
    answer_data = {"image_id": event.message.id}
    await process_survey_answer(event.source.user_id, answer_data, event.reply_token, line_bot_api, db)
