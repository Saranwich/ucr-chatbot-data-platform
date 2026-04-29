from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from linebot.v3.messaging import Configuration, AsyncApiClient, AsyncMessagingApiBlob
from app.config import CHANNEL_ACCESS_TOKEN
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from geoalchemy2.functions import ST_X, ST_Y
from app.database import get_db
from app.models import User, CompletedReport, IncompleteReport
from app.schemas import DashboardStats, CompletedReportSchema
from typing import List, Optional
from datetime import datetime

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

@router.get("/available-dates")
async def get_available_dates(db: AsyncSession = Depends(get_db)):
    # ดึงวันที่ทั้งหมดที่มีการทำรายงาน (CompletedReport)
    query = select(func.date(CompletedReport.created_at).distinct())
    result = await db.execute(query)
    dates = [row[0].strftime("%Y-%m-%d") for row in result.all() if row[0]]
    return {"dates": dates}

@router.get("/reports", response_model=List[CompletedReportSchema])
async def get_completed_reports(date: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    print(f"DEBUG: get_completed_reports called with date={date}")
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
    
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.where(func.date(CompletedReport.created_at) == target_date)
        except ValueError:
            pass # Invalid date format, skip filtering
            
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

@router.get("/image/{image_id}")
async def get_line_image(image_id: str):
    configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    async with AsyncApiClient(configuration) as api_client:
        blob_api = AsyncMessagingApiBlob(api_client)
        content = await blob_api.get_message_content(image_id)
        # Returns the image as a standard response with correct media type
        return Response(content=content, media_type="image/jpeg")
