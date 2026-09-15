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


## session part ##
async def get_session(key: str) -> str | None:
    """ขอ session ทั้งก้อนตาม key — ไม่เคยมีหรือหมดอายุไปแล้วก็คืน None"""
    return await get_client().get(key)


async def save_session(key: str, session: str, ttl: int | None = None) -> None:
    """เขียนทับ session ทั้งก้อน — ใส่ ttl เป็นวินาทีถ้าอยากให้ลืมเองเมื่อเงียบไปนาน

    ไม่ใส่ ttl = อยู่ถาวร และถ้า key เดิมเคยตั้งอายุไว้ การเขียนรอบนี้จะล้างอายุทิ้ง
    """
    await get_client().set(key, session, ex=ttl)


async def scan_session_keys() -> list[str]:
    """ไล่หา key ของ session ที่ยังไม่หมดอายุทั้งหมด — ใช้ scan ไม่ใช่ keys จะได้ไม่ล็อก redis ทั้งตัว"""
    return [key async for key in get_client().scan_iter(match="session:*")]


async def get_ttl(key: str) -> int:
    """อายุที่เหลือเป็นวินาที — -2 คือไม่มี key นี้แล้ว -1 คือมีแต่ไม่ได้ตั้งอายุไว้"""
    return await get_client().ttl(key)


async def delete_session(key: str) -> None:
    """ทิ้ง session ทั้งก้อน — ใช้ตอนปิดบทสนทนา ไม่ต้องรอให้หมดอายุเอง"""
    await get_client().delete(key)
