from uuid import UUID

import httpx

from app.clients import broadcast as client
from app.schemas.broadcast import BroadcastCreate


async def create_draft(text: str, audience: str, user_ids: list[UUID]) -> dict:
    broadcast_id = await client.create_draft(text, audience, user_ids)
    return await client.fetch_broadcast(broadcast_id)


async def request_send(broadcast_id: UUID) -> tuple[dict | None, bool]:
    existing = await client.fetch_broadcast(broadcast_id)
    if existing is None:
        return None, False
    if existing["status"] != "draft" or not await client.begin_send(broadcast_id):
        return await client.fetch_broadcast(broadcast_id), False
    return await client.fetch_broadcast(broadcast_id), True


async def dispatch(broadcast_id: UUID) -> None:
    broadcast = await client.fetch_broadcast(broadcast_id)
    if broadcast is None or broadcast["status"] != "sending":
        return
    while delivery := await client.claim_recipient(broadcast_id):
        try:
            response_status = await client.push_text(
                delivery["line_user_id"], broadcast["text"], delivery["retry_key"]
            )
        except (httpx.TimeoutException, httpx.TransportError) as error:
            # The request may have reached LINE. Keep it unknown and never blindly claim it again.
            await client.finish_recipient(delivery["id"], "unknown", error=type(error).__name__)
        except Exception as error:
            await client.finish_recipient(delivery["id"], "unknown", error=type(error).__name__)
        else:
            status = "sent" if response_status == 200 else "failed"
            await client.finish_recipient(delivery["id"], status, response_status=response_status)
    await client.complete_broadcast(broadcast_id)


async def dispatch_auto(
    text: str, audience: str, user_ids: list[UUID] | None = None
) -> dict | None:
    """Internal gated hook for a future automatic trigger.

    Nothing in runtime calls this hook. With the database gate off (the default), it exits
    before validating, writing a draft, or contacting LINE. When enabled it deliberately
    uses the same durable draft and delivery path as a manual broadcast.
    """
    if not await client.get_auto_enabled():
        return None
    payload = BroadcastCreate(text=text, audience=audience, user_ids=user_ids or [])
    broadcast_id = await client.create_draft(payload.text, payload.audience, payload.user_ids)
    if not await client.begin_send(broadcast_id):
        return await client.fetch_broadcast(broadcast_id)
    await dispatch(broadcast_id)
    return await client.fetch_broadcast(broadcast_id)
