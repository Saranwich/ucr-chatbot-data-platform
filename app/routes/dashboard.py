from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from geoalchemy2.functions import ST_X, ST_Y
from app.database import get_db
from app.models import User, CompletedReport, IncompleteReport
from app.schemas import DashboardStats, CompletedReportSchema
from typing import List

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    user_count = await db.scalar(select(func.count(User.lineuser_id)))
    completed_count = await db.scalar(select(func.count(CompletedReport.report_id)))
    incomplete_count = await db.scalar(select(func.count(IncompleteReport.report_id)))
    
    return {
        "total_users": user_count or 0,
        "total_completed_reports": completed_count or 0,
        "total_incomplete_reports": incomplete_count or 0
    }

@router.get("/reports", response_model=List[CompletedReportSchema])
async def get_completed_reports(db: AsyncSession = Depends(get_db)):
    # ดึงข้อมูลรายงานที่เสร็จสมบูรณ์ พร้อมแปลง Geometry เป็น Lat/Lon
    query = select(
        CompletedReport.report_id,
        CompletedReport.lineuser_id,
        CompletedReport.survey_version,
        CompletedReport.payload,
        CompletedReport.image_path,
        CompletedReport.created_at,
        ST_X(CompletedReport.location_data).label("longitude"),
        ST_Y(CompletedReport.location_data).label("latitude")
    )
    result = await db.execute(query)
    reports = []
    for row in result.mappings():
        reports.append(row)
    return reports

@router.get("/reports/{report_id}", response_model=CompletedReportSchema)
async def get_report_detail(report_id: int, db: AsyncSession = Depends(get_db)):
    query = select(
        CompletedReport.report_id,
        CompletedReport.lineuser_id,
        CompletedReport.survey_version,
        CompletedReport.payload,
        CompletedReport.image_path,
        CompletedReport.created_at,
        ST_X(CompletedReport.location_data).label("longitude"),
        ST_Y(CompletedReport.location_data).label("latitude")
    ).where(CompletedReport.report_id == report_id)
    
    result = await db.execute(query)
    report = result.mappings().first()
    if not report:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")
    return report
