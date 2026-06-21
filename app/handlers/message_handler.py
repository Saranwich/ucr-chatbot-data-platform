from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3.webhooks import TextMessageContent, LocationMessageContent, ImageMessageContent
from app.handlers.info_handler import handle_info_request
from app.handlers.stat_handler import handle_stat_request
from app.handlers.report_handler import handle_report_request
from app.handlers.chatbot_handler import handle_chatbot_chat, handle_chatbot_location, handle_chatbot_image
from app.handlers.manual_handler import handle_manual_request


async def route_message_event(event, line_bot_api, db: AsyncSession):
    """Single router for a MessageEvent: dispatch by content type."""
    message = event.message
    if isinstance(message, TextMessageContent):
        await handle_text_message(event, line_bot_api, db)
    elif isinstance(message, LocationMessageContent):
        await handle_chatbot_location(event, line_bot_api, db)
    elif isinstance(message, ImageMessageContent):
        await handle_chatbot_image(event, line_bot_api, db)


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

    # 4. Route to Chatbot Handler (Default for other text/surveys)
    await handle_chatbot_chat(event, line_bot_api, db, text)
