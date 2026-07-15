"""Conversation memory (V2) — per-user chat transcript in Redis with a TTL.

The LLM is stateless: each turn we re-send the transcript. Redis holds the
live conversation so we don't hit Postgres per message; the TTL auto-expires
abandoned chats. Committed reports go to Postgres later (#93+), not here.

# ponytail: whole transcript stored; #92 windows to the last ~10 messages and
# clears the session on completion.
"""
import json
import os

import redis.asyncio as redis

from app.utils import storage

SESSION_TTL = 1800  # 30 min — abandoned chats expire on their own
_client = None


def _get_client():
    # ponytail: lazy — import ไม่ต้องต่อ Redis, เฉพาะตอนใช้จริงถึงต่อ
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _client = redis.from_url(url, decode_responses=True)
    return _client


def _key(user_id: str) -> str:
    return f"chat:{user_id}"


async def load(user_id: str) -> list[dict]:
    """Transcript so far: [{"role": "user"|"model", "content": str}, ...]."""
    raw = await _get_client().lrange(_key(user_id), 0, -1)
    return [json.loads(x) for x in raw]


async def append(user_id: str, role: str, content: str) -> None:
    """Add one message and refresh the TTL."""
    client, key = _get_client(), _key(user_id)
    await client.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
    await client.expire(key, SESSION_TTL)


# ── broadcast mode flag — session นี้กำลังคุยต่อจาก alert ไหนอยู่ ──
# แทน "ความจำ" ที่เดิมเป็นแถว reports.status (state machine) — ตอนนี้ AI คุยแทน
# flag หมดอายุพร้อมกรอบเวลาเดียวกับ transcript

def _mode_key(user_id: str) -> str:
    return f"broadcast_mode:{user_id}"


async def set_broadcast_mode(user_id: str, alert_type: str) -> None:
    await _get_client().setex(_mode_key(user_id), SESSION_TTL, alert_type)


async def get_broadcast_mode(user_id: str) -> str | None:
    return await _get_client().get(_mode_key(user_id))


async def clear_broadcast_mode(user_id: str) -> None:
    await _get_client().delete(_mode_key(user_id))


# ── ของฝากรอแนบ report — รูป/พิกัดที่ส่งมาระหว่างคุย แนบตอน record_complaint ──
# Gemini คุยเป็น text — ไฟล์/พิกัดไม่เข้าโมเดล แค่พักไว้ที่นี่ (TTL เดียวกับ transcript)
# แล้ว record() hook pop ไปแนบกับ report ที่บันทึก; หมดเวลา = ลืมไปพร้อม session

def _images_key(user_id: str) -> str:
    return f"pending_images:{user_id}"


def _location_key(user_id: str) -> str:
    return f"pending_location:{user_id}"


async def add_pending_image(user_id: str, image_key: str) -> None:
    client, key = _get_client(), _images_key(user_id)
    await client.rpush(key, image_key)
    await client.expire(key, SESSION_TTL)


async def pop_pending_images(user_id: str) -> list[str]:
    """storage keys ของรูปที่รออยู่ทั้งหมด (เคลียร์ทิ้งหลังอ่าน — แนบได้ report เดียว)"""
    client, key = _get_client(), _images_key(user_id)
    keys = await client.lrange(key, 0, -1)
    await client.delete(key)
    return keys


async def set_pending_location(user_id: str, latitude: float, longitude: float) -> None:
    await _get_client().setex(_location_key(user_id), SESSION_TTL, f"{latitude},{longitude}")


async def pop_pending_location(user_id: str) -> tuple[float, float] | None:
    """(lat, lon) ที่รออยู่ หรือ None (เคลียร์ทิ้งหลังอ่าน)"""
    client, key = _get_client(), _location_key(user_id)
    raw = await client.get(key)
    if raw is None:
        return None
    await client.delete(key)
    lat, lon = raw.split(",")
    return float(lat), float(lon)


async def dump_transcript(user_id: str) -> str:
    """Overwrite conversations/<user_id>.json with the transcript so far; return the key.

    # ponytail: dump-on-record archive — sessions otherwise just TTL-expire with no
    # hook, so we snapshot the whole transcript through the storage seam (local
    # uploads/ now, S3 later). Keeps the [{"role","content"}, ...] shape as-is.
    The returned key is stored on the conversation anchor (conversations.archive_key).
    """
    transcript = await load(user_id)
    return storage.save_blob(
        f"conversations/{user_id}.json",
        json.dumps(transcript, ensure_ascii=False).encode("utf-8"),
    )
