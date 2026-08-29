import asyncpg
from app.core.config import DATABASE_URL
from app.schemas.logs import LogsRecord

_pool: asyncpg.Pool | None = None

## app part ##
async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        await init_db()
    return _pool


async def init_db() -> None:
    """ตั้งตารางให้ครบ — ตารางไหนมีอยู่แล้วก็ข้ามไปเงียบ ๆ เรียกจาก init_pool()"""
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id           uuid        PRIMARY KEY,
            time         timestamptz NOT NULL,
            process_name text        NOT NULL,
            log_message  text        NOT NULL
        )
    """)


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("ยังไม่ได้เปิด pool — เรียก init_pool() ตอน startup ก่อน")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


_INSERT_LOG = """
INSERT INTO logs (id, time, process_name, log_message)
VALUES ($1, $2, $3, $4)
"""


async def create_and_save_log(process_name: str, log_message: str) -> None:
    """เรียกด้วยสองสตริงพอ — id กับ time ให้ LogsRecord เติมเอง"""
    log = LogsRecord(process_name=process_name, log_message=log_message)
    await get_pool().execute(
        _INSERT_LOG, log.id, log.time, log.process_name, log.log_message
    )
