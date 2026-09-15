from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import admin, broadcast, line
from app.clients import broadcast as broadcast_client
from app.clients import psql, redis
from app.core.load_env import BASE_DIR
from app.services import runtime
from app.services.config import ai_config, system_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    app.state.pool = await psql.init_pool()
    await broadcast_client.init_db()
    await ai_config.reload()
    await system_config.reload()
    app.state.redis = await redis.init_redis()
    runtime.start()
    print("[app] ready")
    try:
        yield

    finally:

    # --- shutdown ---
        await runtime.stop()
        await psql.close_pool()
        await redis.close_client()
        print("[app] stopped")


app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(line.router)
app.include_router(admin.router)
app.include_router(broadcast.router)
app.mount("/admin", StaticFiles(directory=BASE_DIR / "admin", html=True), name="admin")
