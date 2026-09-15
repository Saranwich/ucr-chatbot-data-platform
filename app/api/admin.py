from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.clients import admin as admin_client
from app.schemas.admin import (
    AdminReportDetail,
    AdminReportPage,
    AdminStatistics,
    AdminUserPage,
)
from app.schemas.report import ProblemType

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/reports", response_model=AdminReportPage)
async def reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    type: ProblemType | None = Query(None),
    days: int | None = Query(None, ge=1, le=365),
):
    return await admin_client.list_reports(limit, offset, type, days)


@router.get("/reports/{report_id}", response_model=AdminReportDetail)
async def report_detail(report_id: UUID):
    report = await admin_client.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/statistics", response_model=AdminStatistics)
async def statistics(days: int = Query(30, ge=1, le=365)):
    return await admin_client.get_statistics(days)


@router.get("/users", response_model=AdminUserPage)
async def users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await admin_client.list_users(limit, offset)


@router.get("/images/{image_id}", response_class=FileResponse)
async def image(image_id: UUID):
    path = await admin_client.get_image_path(image_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)
