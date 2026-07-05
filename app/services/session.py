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
