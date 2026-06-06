from linebot.v3.messaging import ReplyMessageRequest, TextMessage
from app.config import REPORT_DEVELOPMENT_TEXT

async def handle_report_request(event, line_bot_api):
    """
    Handles the 'Report' request from the Rich Menu (Fallback).
    Note: The primary 'Report' action will be a URI redirect to LIFF.
    """
    await line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=REPORT_DEVELOPMENT_TEXT)]
        )
    )
