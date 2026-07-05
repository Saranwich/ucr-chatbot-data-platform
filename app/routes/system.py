"""System endpoints — health check."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    # #75: verify the DB is actually reachable instead of a blind "ok" — a failed
    # DB init should surface as unhealthy (503), not a false green light.
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "database": "unreachable"})
    return {"status": "ok", "database": "ok"}
