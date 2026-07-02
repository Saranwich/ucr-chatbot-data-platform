from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
import traceback
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    Configuration, AsyncApiClient, AsyncMessagingApi, ReplyMessageRequest, TextMessage,
)
from linebot.v3.webhooks import MessageEvent, FollowEvent
from linebot.v3.exceptions import InvalidSignatureError

from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, SURVEYS_DIR, SYSTEM_ERROR_TEXT
from app.database import engine, Base, get_db
from app.handlers.message_handler import route_message_event
from app.handlers.follow_handler import handle_follow
from app.utils.survey_loader import survey_manager
from app.cors import build_cors_origins
from app.routes.dashboard import router as dashboard_router
from app.routes.report import router as report_router
from app.routes.userdata import router as userdata_router
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

# NEW: The "lifespan" context manager is how FastAPI runs code BEFORE the server starts accepting requests
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. จัดการ Database
    try:
        async with engine.begin() as conn:
            # Enable PostGIS extension if not exists
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            
            # Create tables if not exist
            await conn.run_sync(Base.metadata.create_all)

            # users gained profile columns after the table first shipped;
            # create_all never ALTERs existing tables, so add them idempotently here.
            for col in ("nickname", "age_range", "gender", "community"):
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} VARCHAR"))

            # survey_sessions gained pending_multi_select (multi-select accumulator)
            # after the table first shipped — same create_all blind spot. Without this,
            # a DB created before that column crashes every session insert/select.
            await conn.execute(text(
                "ALTER TABLE survey_sessions "
                "ADD COLUMN IF NOT EXISTS pending_multi_select JSON DEFAULT '{}'::json"
            ))

            print("✅ Database tables checked/created with Bangkok timezone defaults!")
    except Exception as e:
        print(f"⚠️ Database initialization warning (likely concurrent start): {e}")

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

FRONTEND_URL = os.getenv("FRONTEND_URL")
FRONTEND_URLS = os.getenv("FRONTEND_URLS")
ENV = os.getenv("ENV", "development")

# Disable Swagger UI and ReDoc in production
docs_url = None if ENV == "production" else "/docs"
redoc_url = None if ENV == "production" else "/redoc"

app = FastAPI(lifespan=lifespan, docs_url=docs_url, redoc_url=redoc_url)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=build_cors_origins(FRONTEND_URL, FRONTEND_URLS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(dashboard_router)
app.include_router(report_router)
app.include_router(userdata_router)

@app.get("/viewer")
async def viewer():
    # ponytail: dev-only data viewer page; API stays JWT-protected
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "viewer.html"))

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Full detail is logged for us only — never returned to the caller.
    print(f"Unhandled Exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

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
            await handle_event_safely(event, line_bot_api, db)

    return 'OK'


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


handler = Mangum(app)
