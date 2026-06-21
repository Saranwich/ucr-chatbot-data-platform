from fastapi import APIRouter, Depends, Response, HTTPException
from app.utils.auth import get_current_user
from app.utils import storage
from fastapi.responses import FileResponse
from linebot.v3.messaging import Configuration, AsyncApiClient, AsyncMessagingApiBlob
from app.config import CHANNEL_ACCESS_TOKEN
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from geoalchemy2.functions import ST_X, ST_Y
from app.database import get_db
from app.models import User, CompletedReport, IncompleteReport, FormReport
from app.schemas import DashboardStats, CompletedReportSchema, IncompleteReportSchema
from app.utils.survey_loader import SurveyManager, survey_manager
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def extract_images(payload: dict) -> list:
    """ดึงรูปทั้งหมดออกมาจาก payload JSONB.

    รูปถูกเก็บใน payload ใต้ key ของคำถาม (ชื่อต่างกันทุก survey เช่น q_photo,
    q_flood_photo) เป็น dict {image_id, image_url}. ฟังก์ชันนี้สแกนหาทุกตัวที่
    เป็น dict มี image_id แล้วรวมเป็นลิสต์เดียว — รองรับ 0, 1, หรือหลายรูป.
    """
    if not isinstance(payload, dict):
        return []
    images = []
    for question_id, value in payload.items():
        if isinstance(value, dict) and value.get("image_id"):
            image_id = value["image_id"]
            images.append({
                "question_id": question_id,
                "image_id": image_id,
                "image_url": value.get("image_url") or f"/api/dashboard/image/{image_id}",
            })
    return images


def parse_date_filter(date: Optional[str]):
    """แปลงค่า filter ?date=YYYY-MM-DD.

    คืน None ถ้าไม่ได้ส่งมา (ไม่กรอง), คืน date ถ้ารูปแบบถูก,
    โยน HTTP 400 ถ้ารูปแบบผิด — แทนที่จะเงียบๆ แล้วคืนทุก record.
    """
    if not date:
        return None
    try:
        return datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")


def resolve_drop_off_question(
    manager: SurveyManager,
    survey_version: str,
    route_id: Optional[str],
    step: Optional[int],
):
    """Resolve a saved route position without failing on changed survey files."""
    if route_id is None or step is None:
        return None, None
    route = manager.get_route(survey_version, route_id)
    if route is None or step < 0 or step >= len(route.questions):
        return None, None
    question_id = route.questions[step]
    question = manager.get_question(survey_version, question_id)
    return question_id, question.text if question else None

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_count = await db.scalar(select(func.count(User.lineuser_id)))
    completed_count = await db.scalar(select(func.count(CompletedReport.report_id)))
    incomplete_count = await db.scalar(select(func.count(IncompleteReport.report_id)))
    
    return {
        "total_users": user_count or 0,
        "total_completed_reports": completed_count or 0,
        "total_incomplete_reports": incomplete_count or 0
    }

@router.get("/available-dates")
async def get_available_dates(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # ดึงวันที่ทั้งหมดที่มีการทำรายงาน (CompletedReport)
    query = select(func.date(CompletedReport.created_at).distinct())
    result = await db.execute(query)
    dates = [row[0].strftime("%Y-%m-%d") for row in result.all() if row[0]]
    return {"dates": dates}

@router.get("/reports", response_model=List[CompletedReportSchema])
async def get_completed_reports(
    date: Optional[str] = None, 
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # ดึงข้อมูลรายงานที่เสร็จสมบูรณ์ พร้อมแปลง Geometry เป็น Lat/Lon
    query = select(
        CompletedReport.report_id,
        CompletedReport.lineuser_id,
        CompletedReport.survey_version,
        CompletedReport.payload,
        CompletedReport.created_at,
        ST_X(CompletedReport.location_data).label("longitude"),
        ST_Y(CompletedReport.location_data).label("latitude")
    )

    target_date = parse_date_filter(date)
    if target_date:
        query = query.where(func.date(CompletedReport.created_at) == target_date)

    result = await db.execute(query)
    reports = []
    for row in result.mappings():
        item = dict(row)
        item["images"] = extract_images(item.get("payload"))
        reports.append(item)
    return reports


@router.get("/incomplete-reports", response_model=List[IncompleteReportSchema])
async def get_incomplete_reports(
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = select(
        IncompleteReport.report_id,
        IncompleteReport.lineuser_id,
        IncompleteReport.survey_version,
        IncompleteReport.drop_off_route_id,
        IncompleteReport.drop_off_step,
        IncompleteReport.payload,
        IncompleteReport.status,
        IncompleteReport.created_at,
        ST_X(IncompleteReport.location_data).label("longitude"),
        ST_Y(IncompleteReport.location_data).label("latitude"),
    ).order_by(IncompleteReport.created_at.desc())

    target_date = parse_date_filter(date)
    if target_date:
        query = query.where(func.date(IncompleteReport.created_at) == target_date)

    result = await db.execute(query)
    reports = []
    for row in result.mappings():
        item = dict(row)
        question_id, question_text = resolve_drop_off_question(
            survey_manager,
            item["survey_version"],
            item["drop_off_route_id"],
            item["drop_off_step"],
        )
        item["drop_off_question_id"] = question_id
        item["drop_off_question_text"] = question_text
        reports.append(item)
    return reports

@router.get("/form-reports")
async def get_form_reports(
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # แจ้งปัญหาจาก LIFF form — รูปเสิร์ฟผ่าน /api/form-reports/{id}/image (ไม่ใช่ payload)
    query = select(
        FormReport.report_id,
        FormReport.lineuser_id,
        FormReport.category,
        FormReport.description,
        FormReport.status,
        FormReport.image_path,
        FormReport.created_at,
        ST_X(FormReport.location_data).label("longitude"),
        ST_Y(FormReport.location_data).label("latitude"),
    ).order_by(FormReport.created_at.desc())

    target_date = parse_date_filter(date)
    if target_date:
        query = query.where(func.date(FormReport.created_at) == target_date)

    result = await db.execute(query)
    reports = []
    for row in result.mappings():
        item = dict(row)
        item["image_url"] = (
            f"/api/form-reports/{item['report_id']}/image" if item["image_path"] else None
        )
        reports.append(item)
    return reports

@router.get("/reports/{report_id}", response_model=CompletedReportSchema)
async def get_report_detail(
    report_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    query = select(
        CompletedReport.report_id,
        CompletedReport.lineuser_id,
        CompletedReport.survey_version,
        CompletedReport.payload,
        CompletedReport.created_at,
        ST_X(CompletedReport.location_data).label("longitude"),
        ST_Y(CompletedReport.location_data).label("latitude")
    ).where(CompletedReport.report_id == report_id)

    result = await db.execute(query)
    report = result.mappings().first()
    if not report:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")
    item = dict(report)
    item["images"] = extract_images(item.get("payload"))
    return item

async def fetch_image_content(blob_api, image_id: str) -> bytes:
    """ดึง bytes รูปจาก LINE CDN.

    รูปถูก proxy สดจาก LINE ซึ่งลบทิ้งหลังผ่านไปสักพัก. ถ้ารูปหมดอายุ/หาไม่เจอ
    โยน HTTP 404 แทนที่จะปล่อยให้ exception หลุดไปเป็น 500.
    """
    try:
        return await blob_api.get_message_content(image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found or expired")

@router.get("/image/{image_id}")
async def get_line_image(
    image_id: str,
    current_user: dict = Depends(get_current_user)
):
    # รูปที่เก็บถาวรแล้ว (survey/<image_id>.jpg) เสิร์ฟจาก store ตรง ๆ —
    # ของเก่าก่อนมีระบบเก็บค่อย fallback ไป proxy สดจาก LINE CDN จนกว่าจะหมดอายุ
    stored = storage.local_file(f"survey/{image_id}.jpg")
    if stored:
        return FileResponse(stored, media_type="image/jpeg")

    configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    async with AsyncApiClient(configuration) as api_client:
        blob_api = AsyncMessagingApiBlob(api_client)
        content = await fetch_image_content(blob_api, image_id)
        # Returns the image as a standard response with correct media type
        return Response(content=content, media_type="image/jpeg")
