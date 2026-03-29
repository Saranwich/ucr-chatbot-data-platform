from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from linebot.v3 import WebhookParser
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError

from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN
from app.database import engine, Base, get_db

# Import Handler ที่เราเพิ่งสร้าง
from app.handlers.message_handler import handle_text_message

Base.metadata.create_all(bind=engine)

app = FastAPI()

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(CHANNEL_SECRET)

@app.post("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    signature = request.headers.get('x-line-signature', '')
    body = await request.body()
    body_text = body.decode('utf-8')

    try:
        events = parser.parse(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        for event in events:
            # ตอนนี้ดักแค่ Text Message ก่อน
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                # โยนให้ Handler จัดการต่อ
                handle_text_message(event, db, line_bot_api)

    return 'OK'