from redis.asyncio import Redis

from app.core.config import REDIS_URL

_client: Redis | None = None


## app part ##
async def init_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(REDIS_URL, decode_responses=True)
        await _client.ping()
    return _client


def get_client() -> Redis:
    if _client is None:
        raise RuntimeError("ยังไม่ได้เปิด client — เรียก init_redis() ตอน startup ก่อน")
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
