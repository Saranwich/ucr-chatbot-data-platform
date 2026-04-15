from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3 import WebhookParser
from linebot.v3.messaging import Configuration, AsyncApiClient, AsyncMessagingApi
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent, ImageMessageContent
from linebot.v3.exceptions import InvalidSignatureError

from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, SURVEY_QUESTIONS
from app.database import engine, Base, get_db
from app.handlers.message_handler import handle_text_message, handle_location_message, handle_image_message
from app.utils.survey_loader import survey_manager

# NEW: The "lifespan" context manager is how FastAPI runs code BEFORE the server starts accepting requests
@asynccontextmanager
async def lifespan(app: FastAPI):
    # This block runs ONE TIME when you start uvicorn
    async with engine.begin() as conn:
        # We use create_all to ensure tables exist. 
        # (Note: In a real production app, you should use Alembic for migrations instead of this)

        await conn.run_sync(Base.metadata.create_all)
        print("Database tables checked/created successfully!")

        try:
            # สมมติว่ารันจาก root directory ของโปรเจกต์
            survey_path = SURVEY_QUESTIONS
            survey_manager.load_from_file(survey_path)
        except Exception as e:
            print(f"Failed to load survey JSON: {e}")
            # ถ้าโหลด JSON ไม่ผ่าน ให้หยุดการรันเซิร์ฟเวอร์ไปเลย จะได้รู้ตัวว่าไฟล์พัง!
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