from linebot.v3.messaging import ReplyMessageRequest, TextMessage
from app.config import PROJECT_INFO_TEXT

async def handle_info_request(event, line_bot_api):
    """Handles the 'Project Info' request from the Rich Menu."""
    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=PROJECT_INFO_TEXT)]
        )
    )
