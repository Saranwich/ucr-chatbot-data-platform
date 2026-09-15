from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status

from app.clients import broadcast as client
from app.schemas.broadcast import (
    BroadcastCreate,
    BroadcastDetail,
    BroadcastList,
    BroadcastSettings,
    BroadcastSummary,
)
from app.services import broadcast as service

router = APIRouter(prefix="/api/admin", tags=["admin broadcasts"])


@router.post("/broadcasts", response_model=BroadcastSummary, status_code=status.HTTP_201_CREATED)
async def create_broadcast(payload: BroadcastCreate):
    try:
        return await service.create_draft(payload.text, payload.audience, payload.user_ids)
    except client.UnknownBroadcastUsersError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Some selected users do not exist",
                "user_ids": [str(user_id) for user_id in error.user_ids],
            },
        ) from error


@router.post("/broadcasts/{broadcast_id}/send", response_model=BroadcastSummary, status_code=status.HTTP_202_ACCEPTED)
async def send_broadcast(broadcast_id: UUID, background_tasks: BackgroundTasks, response: Response):
    item, accepted = await service.request_send(broadcast_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if not accepted:
        raise HTTPException(status_code=409, detail="Broadcast has already been sent")
    background_tasks.add_task(service.dispatch, broadcast_id)
    response.status_code = status.HTTP_202_ACCEPTED
    return item


@router.get("/broadcasts", response_model=BroadcastList)
async def get_broadcasts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = await client.list_broadcasts(limit, offset)
    return {"items": items, "total": total}


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastDetail)
async def get_broadcast(broadcast_id: UUID):
    item = await client.fetch_broadcast(broadcast_id, include_recipients=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return item


@router.get("/broadcast-settings", response_model=BroadcastSettings)
async def get_broadcast_settings():
    # The DB value gates the internal hook; there is deliberately no scheduler or auto trigger.
    enabled = await client.get_auto_enabled()
    return {"auto_enabled": enabled, "configured_auto_enabled": enabled}
