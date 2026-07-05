"""LINE webhook — POST /callback.

Validates the signed webhook, then dispatches each event to its handler. A
per-event rescue keeps one failing event from leaving the user in silence.
"""
import traceback

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    Configuration, AsyncApiClient, AsyncMessagingApi, ReplyMessageRequest, TextMessage,
)
from linebot.v3.webhooks import MessageEvent, FollowEvent
from linebot.v3.exceptions import InvalidSignatureError

from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, SYSTEM_ERROR_TEXT
from app.database import get_db
from app.handlers.message_handler import route_message_event
from app.handlers.follow_handler import handle_follow

router = APIRouter(tags=["line"])

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(CHANNEL_SECRET)


@router.post("/callback")
async def callback(request: Request, db: AsyncSession = Depends(get_db)):
    signature = request.headers.get("x-line-signature", "")
    body_text = (await request.body()).decode("utf-8")

    try:
        events = parser.parse(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    async with AsyncApiClient(configuration) as api_client:
        line_bot_api = AsyncMessagingApi(api_client)
        for event in events:
            await handle_event_safely(event, line_bot_api, db)

    return "OK"


async def handle_event_safely(event, line_bot_api, db):
    """Run one webhook event; on any failure, tell the user to retry instead of
    leaving them staring at silence.

    The rescue reply is best-effort: if it ALSO fails (network to LINE down, or a
    reply_token already spent) we just log it — a failing rescue must not crash
    the request. No DB commit happens on the failing path (get_db never
    auto-commits), so the user's retry re-answers the same question cleanly.
    """
    try:
        if isinstance(event, MessageEvent):
            await route_message_event(event, line_bot_api, db)
        elif isinstance(event, FollowEvent):
            await handle_follow(event, line_bot_api, db)
    except Exception:
        print(f"callback event failed: {traceback.format_exc()}")
        reply_token = getattr(event, "reply_token", None)
        if reply_token:
            try:
                await line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=SYSTEM_ERROR_TEXT)],
                    )
                )
            except Exception:
                print(f"emergency reply failed: {traceback.format_exc()}")
