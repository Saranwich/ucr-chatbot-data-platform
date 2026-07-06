from contextlib import asynccontextmanager
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.cors import build_cors_origins
from app.routes.dashboard import router as dashboard_router
from app.routes.report import router as report_router
from app.routes.userdata import router as userdata_router
from app.routes.line import router as line_router
from app.routes.viewer import router as viewer_router
from app.routes.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is Alembic-owned now (alembic upgrade head as a deploy step) — the app
    # no longer runs create_all/ALTER at boot. See alembic/versions/. The dormant V1
    # survey-JSON load was removed in M4 (legacy tables dropped, survey_loader deleted).
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
