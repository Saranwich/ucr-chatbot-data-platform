from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3 import WebhookParser
from linebot.v3.messaging import Configuration, AsyncApiClient, AsyncMessagingApi
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent, ImageMessageContent
from linebot.v3.exceptions import InvalidSignatureError

from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, SURVEYS_DIR
from app.database import engine, Base, get_db
from app.handlers.message_handler import handle_text_message, handle_location_message, handle_image_message
from app.utils.survey_loader import survey_manager

# NEW: The "lifespan" context manager is how FastAPI runs code BEFORE the server starts accepting requests
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. จัดการ Database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables checked/created successfully!")

    # 2. จัดการโหลด Survey JSON ทั้งโฟลเดอร์
    try:
        # ใช้ฟังก์ชันใหม่ที่เราเพิ่งสร้าง ชี้ไปที่โฟลเดอร์ SURVEYS_DIR
        survey_manager.load_all_surveys_in_directory(SURVEYS_DIR)
        print("✅ All survey JSONs loaded successfully during startup!")
    except Exception as e:
        print(f"❌ Failed to load survey JSONs: {e}")
        # ถ้าโหลดไม่ผ่าน (เช่น โฟลเดอร์ไม่มี หรือไฟล์ JSON พัง) ให้หยุดเซิร์ฟเวอร์ไปเลย
        raise e
        
    yield
    # (Anything below the yield runs when the server is shutting down)

app = FastAPI(lifespan=lifespan)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(CHANNEL_SECRET)

# Notice how the Dependency now asks for an AsyncSession
@app.post("/callback")
async def callback(request: Request, db: AsyncSession = Depends(get_db)):
    signature = request.headers.get('x-line-signature', '')
    body = await request.body()
    body_text = body.decode('utf-8')

    try:
        events = parser.parse(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    async with AsyncApiClient(configuration) as api_client:
        line_bot_api = AsyncMessagingApi(api_client)

        for event in events:
            if isinstance(event, MessageEvent):
                # ถ้าเป็นข้อความตัวอักษร หรือ Quick Reply แบบ message
                if isinstance(event.message, TextMessageContent):
                    await handle_text_message(event, line_bot_api, db)
                
                # ถ้าเป็นพิกัด (Location)
                elif isinstance(event.message, LocationMessageContent):
                    await handle_location_message(event, line_bot_api, db)
                
                # ถ้าเป็นรูปภาพ (เผื่อไว้สำหรับคำถามข้อสุดท้ายเลย)
                elif isinstance(event.message, ImageMessageContent):
                    await handle_image_message(event, line_bot_api, db)

    return 'OK'