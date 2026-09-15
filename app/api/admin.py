from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.clients import psql
from app.schemas.broadcast import (
    BroadcastCreate,
    BroadcastDetail,
    BroadcastList,
    BroadcastSummary,
)
from app.schemas.system_config import SystemConfig
from app.services import broadcast as service
from app.services.config import system_config

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/broadcasts", response_model=BroadcastSummary, status_code=status.HTTP_202_ACCEPTED)
async def create_broadcast(payload: BroadcastCreate, force_send: bool = Query(default=False)):
    try:
        return await service.send(
            payload.text, payload.audience, payload.user_ids, force_send
        )
    except psql.UnknownBroadcastUsersError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Some selected users do not exist",
                "user_ids": [str(user_id) for user_id in error.user_ids],
            },
        ) from error


@router.get("/broadcasts", response_model=BroadcastList)
async def get_broadcasts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = await psql.get_broadcasts(limit, offset)
    return {"items": items, "total": total}


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastDetail)
async def get_broadcast(broadcast_id: UUID):
    item = await psql.get_broadcast(broadcast_id, include_recipients=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return item


@router.get("/system-config", response_model=SystemConfig)
async def get_system_config():
    return system_config.get()
