"""Admin dashboard API — thin endpoints. Logic lives in services/dashboard.py."""
from typing import Optional

from fastapi import APIRouter, Depends, Response, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import get_current_user
from app.services import dashboard as svc

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await svc.get_stats(db)


@router.get("/available-dates")
async def get_available_dates(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await svc.get_available_dates(db)


@router.get("/reports")
async def get_completed_reports(
    date: Optional[str] = None,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    problem_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await svc.list_completed(db, date, date_from, date_to, problem_type, page, limit)


@router.get("/incomplete-reports")
async def get_incomplete_reports(
    date: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await svc.list_incomplete(db, date, page, limit)


@router.get("/form-reports")
async def get_form_reports(
    date: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await svc.list_form(db, date, page, limit)


@router.get("/broadcast-reports")
async def get_broadcast_reports(
    date: Optional[str] = None,
    alert_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await svc.list_broadcast(db, date, alert_type, page, limit)


@router.get("/reports/{report_id}")
async def get_report_detail(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await svc.get_report_detail(db, report_id)


@router.get("/image/{image_id}")
async def get_line_image(
    image_id: str,
    current_user: dict = Depends(get_current_user),
):
    # รูปที่เก็บถาวรแล้วเสิร์ฟจาก store ตรง ๆ — ของเก่า fallback ไป proxy สดจาก LINE CDN
    stored = svc.survey_image_path(image_id)
    if stored:
        return FileResponse(stored, media_type="image/jpeg")
    content = await svc.fetch_line_image_bytes(image_id)
    return Response(content=content, media_type="image/jpeg")


@router.get("/broadcast-image/{report_id}")
async def get_broadcast_image(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    stored = await svc.broadcast_image_path(db, report_id)
    return FileResponse(stored, media_type="image/jpeg")
