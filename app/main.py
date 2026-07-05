from contextlib import asynccontextmanager
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from mangum import Mangum

from app.config import SURVEYS_DIR
from app.database import engine, Base
from app.utils.survey_loader import survey_manager
from app.cors import build_cors_origins
from app.routes.dashboard import router as dashboard_router
from app.routes.report import router as report_router
from app.routes.userdata import router as userdata_router
from app.routes.line import router as line_router
from app.routes.viewer import router as viewer_router
from app.routes.system import router as system_router


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

            # broadcast_reports gained flow-state + note columns after first ship —
            # same create_all blind spot; add idempotently. DEFAULT 'done' ให้แถวเก่า
            # (สร้างก่อนมี column) ถือเป็นรายงานที่จบแล้ว
            await conn.execute(text(
                "ALTER TABLE broadcast_reports ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'done'"
            ))
            await conn.execute(text(
                "ALTER TABLE broadcast_reports ADD COLUMN IF NOT EXISTS note VARCHAR"
            ))

            print("✅ Database tables checked/created with Bangkok timezone defaults!")
    except Exception as e:
        print(f"⚠️ Database initialization warning (likely concurrent start): {e}")

    # 2. โหลด Survey JSON ทั้งโฟลเดอร์ (dashboard ยังอ่านข้อมูลสำรวจเก่าอยู่)
    try:
        survey_manager.load_all_surveys_in_directory(SURVEYS_DIR)
        print("✅ All survey JSONs loaded successfully during startup!")
    except Exception as e:
        print(f"❌ Failed to load survey JSONs: {e}")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=build_cors_origins(FRONTEND_URL, FRONTEND_URLS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — endpoints live in app/routes/, main.py only binds them
app.include_router(line_router)
app.include_router(dashboard_router)
app.include_router(report_router)
app.include_router(userdata_router)
app.include_router(viewer_router)
app.include_router(system_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Full detail is logged for us only — never returned to the caller.
    print(f"Unhandled Exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


handler = Mangum(app)
