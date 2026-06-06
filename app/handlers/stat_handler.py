from linebot.v3.messaging import ReplyMessageRequest, TextMessage
from app.config import SUMMARY_PLACEHOLDER_TEXT

async def handle_stat_request(event, line_bot_api):
    """Handles the 'Summaries' request from the Rich Menu."""
    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=SUMMARY_PLACEHOLDER_TEXT)]
        )
    )
