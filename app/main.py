import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.cors import build_cors_origins
from app.routes.broadcast import router as broadcast_router
from app.routes.dashboard import router as dashboard_router
from app.routes.report import router as report_router
from app.routes.userdata import router as userdata_router
from app.routes.line import router as line_router
from app.routes.viewer import router as viewer_router
from app.routes.system import router as system_router
from app.services.weather import run_broadcast

_BANGKOK = timezone(timedelta(hours=7))


async def _broadcast_scheduler():
    """ตื่นทุกต้นชั่วโมง (เวลาไทย) → ยิง broadcast เฉพาะ event ที่ถึงเวลาในชั่วโมงนั้น

    เวลายิงมาจาก `time` ในไฟล์ forecast เอง ไม่ fix รายวัน — run_broadcast(only_due=True)
    เป็นคนกรอง. พังรอบไหน log แล้วรอรอบถัดไป ห้ามให้ task ตาย.
    # ponytail: asyncio loop ใช้ได้เฉพาะ process ยาวๆ (uvicorn) — บน Lambda ไม่ทำงาน,
    # ย้ายไป EventBridge ตอน deploy จริง (sprint หน้า)
    """
    while True:
        now = datetime.now(_BANGKOK)
        next_tick = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        await asyncio.sleep((next_tick - now).total_seconds())
        try:
            summary = await run_broadcast(only_due=True)
            if summary["sent"] or summary["failed"] or summary["unmatched"]:
                print(f"⏰ broadcast tick: {summary}")
        except Exception:
            print(f"broadcast scheduler tick failed: {traceback.format_exc()}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is Alembic-owned now (alembic upgrade head as a deploy step) — the app
    # no longer runs create_all/ALTER at boot. See alembic/versions/. The dormant V1
    # survey-JSON load was removed in M4 (legacy tables dropped, survey_loader deleted).
    scheduler = asyncio.create_task(_broadcast_scheduler())
    yield
    # (Anything below the yield runs when the server is shutting down)
    scheduler.cancel()


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
app.include_router(broadcast_router)
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
