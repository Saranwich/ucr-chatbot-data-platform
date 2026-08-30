from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import line
from app.clients import psql, redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    app.state.pool = await psql.init_pool()
    app.state.redis = await redis.init_redis()
    print("app opened")
    try:
        yield

    finally:

    # --- shutdown ---
        await psql.close_pool()
        await redis.close_client()
        print("app closed")


app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(line.router)
