from linebot.v3.messaging import ReplyMessageRequest, TextMessage
from app.config import MANUAL_TEXT

async def handle_manual_request(event, line_bot_api):
    """Handles the 'คู่มือการใช้งาน' request from the Rich Menu."""
    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=MANUAL_TEXT)]
        )
    )
