from typing import Any
from uuid import UUID, uuid4

import httpx

from app.clients import psql
from app.core.config import LINE_CHANNEL_ACCESS_TOKEN

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
TIMEOUT = 10


class UnknownBroadcastUsersError(ValueError):
    def __init__(self, user_ids: list[UUID]):
        self.user_ids = user_ids
        super().__init__("Some selected users do not exist")


async def init_db() -> None:
    """Create durable broadcast storage after the main PostgreSQL pool starts."""
    pool = psql.get_pool()
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_settings (
            singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            auto_enabled boolean NOT NULL DEFAULT false
        )
    """)
    await pool.execute("""
        INSERT INTO broadcast_settings (singleton, auto_enabled)
        VALUES (true, false) ON CONFLICT (singleton) DO NOTHING
    """)
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id uuid PRIMARY KEY,
            text text NOT NULL CHECK (text <> ''),
            audience text NOT NULL CHECK (audience IN ('all', 'selected')),
            user_ids uuid[] NOT NULL DEFAULT '{}',
            status text NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'sending', 'completed')),
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            completed_at timestamptz
        )
    """)
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_deliveries (
            id uuid PRIMARY KEY,
            broadcast_id uuid NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            line_user_id text NOT NULL,
            retry_key uuid NOT NULL UNIQUE,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'unknown')),
            attempted_at timestamptz,
            completed_at timestamptz,
            response_status integer,
            error text,
            UNIQUE (broadcast_id, user_id)
        )
    """)
    await pool.execute("""
        CREATE INDEX IF NOT EXISTS broadcast_deliveries_broadcast_status
        ON broadcast_deliveries (broadcast_id, status)
    """)


async def create_draft(text: str, audience: str, user_ids: list[UUID]) -> UUID:
    broadcast_id = uuid4()
    pool = psql.get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """INSERT INTO broadcasts (id, text, audience, user_ids)
                   VALUES ($1, $2, $3, $4)""",
                broadcast_id, text, audience, user_ids,
            )
            if audience == "all":
                users = await connection.fetch("SELECT id, line_user_id FROM users")
            else:
                users = await connection.fetch(
                    "SELECT id, line_user_id FROM users WHERE id = ANY($1::uuid[])", user_ids
                )
                found_ids = {row["id"] for row in users}
                missing_ids = [user_id for user_id in user_ids if user_id not in found_ids]
                if missing_ids:
                    # Raised inside the transaction so the draft insert is rolled back too.
                    raise UnknownBroadcastUsersError(missing_ids)
            await connection.executemany(
                """INSERT INTO broadcast_deliveries
                   (id, broadcast_id, user_id, line_user_id, retry_key)
                   VALUES ($1, $2, $3, $4, $5)""",
                [(uuid4(), broadcast_id, row["id"], row["line_user_id"], uuid4()) for row in users],
            )
    return broadcast_id


async def begin_send(broadcast_id: UUID) -> bool:
    result = await psql.get_pool().execute(
        """UPDATE broadcasts SET status = 'sending', started_at = now()
           WHERE id = $1 AND status = 'draft'""", broadcast_id
    )
    return result == "UPDATE 1"


async def claim_recipient(broadcast_id: UUID) -> dict[str, Any] | None:
    row = await psql.get_pool().fetchrow(
        """UPDATE broadcast_deliveries SET status = 'sending', attempted_at = now()
           WHERE id = (
               SELECT id FROM broadcast_deliveries
               WHERE broadcast_id = $1 AND status = 'pending'
               ORDER BY user_id FOR UPDATE SKIP LOCKED LIMIT 1
           )
           RETURNING id, user_id, line_user_id, retry_key""", broadcast_id
    )
    return dict(row) if row else None


async def finish_recipient(
    delivery_id: UUID, status: str, response_status: int | None = None, error: str | None = None
) -> None:
    await psql.get_pool().execute(
        """UPDATE broadcast_deliveries
           SET status = $2, response_status = $3, error = $4, completed_at = now()
           WHERE id = $1 AND status = 'sending'""",
        delivery_id, status, response_status, error,
    )


async def complete_broadcast(broadcast_id: UUID) -> None:
    await psql.get_pool().execute(
        """UPDATE broadcasts SET status = 'completed', completed_at = now()
           WHERE id = $1 AND status = 'sending'
             AND NOT EXISTS (
               SELECT 1 FROM broadcast_deliveries
               WHERE broadcast_id = $1 AND status IN ('pending', 'sending')
             )""", broadcast_id,
    )


async def fetch_broadcast(broadcast_id: UUID, include_recipients: bool = False) -> dict | None:
    row = await psql.get_pool().fetchrow(_DETAIL_SQL, broadcast_id)
    if row is None:
        return None
    result = _normalise(row)
    if include_recipients:
        rows = await psql.get_pool().fetch(
            """SELECT user_id, status, attempted_at, completed_at, response_status, error
               FROM broadcast_deliveries WHERE broadcast_id = $1 ORDER BY user_id""", broadcast_id
        )
        result["recipients"] = [dict(item) for item in rows]
    return result


async def list_broadcasts(limit: int, offset: int) -> tuple[list[dict], int]:
    pool = psql.get_pool()
    rows = await pool.fetch(
        _DETAIL_SQL + " ORDER BY b.created_at DESC LIMIT $2 OFFSET $3", None, limit, offset
    )
    total = await pool.fetchval("SELECT count(*)::int FROM broadcasts")
    return [_normalise(row) for row in rows], total


async def get_auto_enabled() -> bool:
    value = await psql.get_pool().fetchval(
        "SELECT auto_enabled FROM broadcast_settings WHERE singleton = true"
    )
    # Auto mode is deliberately fail-closed. There is no scheduler or automatic dispatcher.
    return value is True


async def push_text(line_user_id: str, text: str, retry_key: UUID) -> int:
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Line-Retry-Key": str(retry_key),
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            LINE_PUSH_URL,
            headers=headers,
            json={"to": line_user_id, "messages": [{"type": "text", "text": text}]},
        )
    return response.status_code


_DETAIL_SQL = """
SELECT b.id, b.text, b.audience, b.user_ids, b.status, b.created_at,
       count(d.id)::int AS recipient_count,
       count(d.id) FILTER (WHERE d.status = 'pending')::int AS pending,
       count(d.id) FILTER (WHERE d.status = 'sending')::int AS sending,
       count(d.id) FILTER (WHERE d.status = 'sent')::int AS sent,
       count(d.id) FILTER (WHERE d.status = 'failed')::int AS failed,
       count(d.id) FILTER (WHERE d.status = 'unknown')::int AS unknown
FROM broadcasts b LEFT JOIN broadcast_deliveries d ON d.broadcast_id = b.id
WHERE ($1::uuid IS NULL OR b.id = $1)
GROUP BY b.id
"""


def _normalise(row) -> dict:
    item = dict(row)
    item["user_ids"] = list(item.get("user_ids") or [])
    item["counts"] = {key: item.pop(key) for key in ("pending", "sending", "sent", "failed", "unknown")}
    return item
