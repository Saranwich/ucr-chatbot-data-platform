"""Dashboard data layer — queries + serialization for the admin API.

Routes in routes/dashboard.py stay thin and call these. Same JSON contract as
before; this only moves the logic out of the route module (main→routes→services).

# ponytail: these raise HTTPException (400/404) directly — fine for one small app;
# not worth a separate error-translation layer.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y
from linebot.v3.messaging import Configuration, AsyncApiClient, AsyncMessagingApiBlob

from app.config import CHANNEL_ACCESS_TOKEN
from app.models import User, CompletedReport, IncompleteReport, FormReport, BroadcastReport
from app.utils import storage
from app.utils.survey_loader import SurveyManager, survey_manager

BANGKOK = timezone(timedelta(hours=7))


# ── serialization helpers ────────────────────────────────────────────────────
def with_offset(dt: Optional[datetime]):
    """แปะ +07:00 ให้ค่าที่เก็บเป็นเวลา Bangkok แบบ naive.

    DB เก็บ wall-clock ของ Bangkok ไว้แบบไม่มี tzinfo — ถ้าส่งดิบ ๆ frontend จะ
    ตีความเป็น UTC. แปะ tz ให้ FastAPI serialize ออกมาเป็น ...+07:00.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=BANGKOK)
    return dt


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


def problem_type_of(payload) -> Optional[str]:
    """ประเภทปัญหา = คำตอบข้อแรก (q_start) เช่น อากาศร้อน / น้ำท่วม / ขยะ."""
    return payload.get("q_start") if isinstance(payload, dict) else None


def serialize_completed(row: dict) -> dict:
    payload = row["payload"]
    images = extract_images(payload)
    lat, lon = row["latitude"], row["longitude"]
    return {
        "report_id": row["report_id"],
        "lineuser_id": row["lineuser_id"],
        "source": "survey",
        "survey_version": row["survey_version"],
        "problem_type": problem_type_of(payload),
        "status": "completed",
        "is_complete": True,
        "latitude": lat,
        "longitude": lon,
        "has_location": lat is not None and lon is not None,
        "images": images,
        "has_image": bool(images),
        "payload": payload,
        "created_at": with_offset(row["created_at"]),
    }


def serialize_incomplete(row: dict, question_id, question_text) -> dict:
    payload = row["payload"]
    images = extract_images(payload)
    lat, lon = row["latitude"], row["longitude"]
    return {
        "report_id": row["report_id"],
        "lineuser_id": row["lineuser_id"],
        "source": "survey",
        "survey_version": row["survey_version"],
        "problem_type": problem_type_of(payload),
        "status": row["status"],
        "is_complete": False,
        "latitude": lat,
        "longitude": lon,
        "has_location": lat is not None and lon is not None,
        "images": images,
        "has_image": bool(images),
        "drop_off_route_id": row["drop_off_route_id"],
        "drop_off_step": row["drop_off_step"],
        "drop_off_question_id": question_id,
        "drop_off_question_text": question_text,
        "payload": payload,
        "created_at": with_offset(row["created_at"]),
    }


def serialize_form(row: dict) -> dict:
    lat, lon = row["latitude"], row["longitude"]
    has_image = bool(row["image_path"])
    return {
        "report_id": row["report_id"],
        "lineuser_id": row["lineuser_id"],
        "source": "form_report",
        "category": row["category"],
        "description": row["description"],
        "status": row["status"],
        "latitude": lat,
        "longitude": lon,
        "has_location": lat is not None and lon is not None,
        "image_url": f"/api/form-reports/{row['report_id']}/image" if has_image else None,
        "has_image": has_image,
        "created_at": with_offset(row["created_at"]),
    }


# broadcast alert_type (code) → ชื่อหมวดไทยที่ dashboard group (align กับ survey/form)
# "both" map เป็น 2 หมวด → serialize จะแตกเป็น 2 หมุดบนแผนที่
BROADCAST_CATEGORY = {
    "flood": ["น้ำท่วม/น้ำขัง"],           # ตรงทั้ง survey + form
    "heat":  ["อากาศร้อน"],                # ตาม survey (form ใช้ "ความร้อน/อุณหภูมิ" — รอ align)
    "both":  ["น้ำท่วม/น้ำขัง", "อากาศร้อน"],  # ← both = 2 หมุด
}


def serialize_broadcast(row: dict) -> list:
    """ปั้น broadcast report 1 แถว → list ของ item สำหรับ dashboard.

    flood/heat → 1 item, both → 2 item (คนละ category แต่ location/รูป/เวลาเหมือนกัน)
    """
    lat, lon = row["latitude"], row["longitude"]
    has_image = bool(row["image_path"])
    base = {
        "report_id": row["report_id"],
        "lineuser_id": row["lineuser_id"],
        "source": "broadcast",
        "alert_type": row["alert_type"],
        "confirmed": bool(row["confirmed"]),
        "community": row["community"],
        "note": row["note"],
        "latitude": lat,
        "longitude": lon,
        "has_location": lat is not None and lon is not None,
        "image_url": f"/api/dashboard/broadcast-image/{row['report_id']}" if has_image else None,  # TODO: endpoint เสิร์ฟรูป
        "has_image": has_image,
        "created_at": with_offset(row["created_at"]),
    }
    # แตกตาม category ที่ map ไว้ (both → 2 item)
    return [{**base, "category": cat} for cat in BROADCAST_CATEGORY.get(row["alert_type"], [])]


def envelope(items: list, page: int, limit: int) -> dict:
    """หุ้ม list ด้วย {items,total,page,limit} + แบ่งหน้า.

    ponytail: slice ใน Python เพราะข้อมูลยังเล็ก (หลักสิบ). ถ้าโตค่อยดัน
    LIMIT/OFFSET ลง SQL.
    """
    total = len(items)
    start = (page - 1) * limit
    return {"items": items[start:start + limit], "total": total, "page": page, "limit": limit}


def parse_date_filter(date: Optional[str]):
    """แปลง YYYY-MM-DD → date. None ถ้าไม่ส่ง, 400 ถ้ารูปแบบผิด."""
    if not date:
        return None
    try:
        return datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")


def apply_date_range(query, column, date, date_from, date_to):
    d = parse_date_filter(date)
    if d:
        query = query.where(func.date(column) == d)
    df = parse_date_filter(date_from)
    if df:
        query = query.where(func.date(column) >= df)
    dt = parse_date_filter(date_to)
    if dt:
        query = query.where(func.date(column) <= dt)
    return query


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


# ── queries (each takes a db session, returns dashboard-ready data) ───────────
async def get_stats(db: AsyncSession) -> dict:
    user_count = await db.scalar(select(func.count(User.lineuser_id)))
    incomplete_count = await db.scalar(select(func.count(IncompleteReport.report_id)))

    rows = (await db.execute(select(
        CompletedReport.survey_version,
        CompletedReport.payload,
        CompletedReport.created_at,
        ST_X(CompletedReport.location_data).label("longitude"),
        ST_Y(CompletedReport.location_data).label("latitude"),
    ))).mappings().all()

    by_problem_type: dict = {}
    by_survey_version: dict = {}
    daily: dict = {}
    with_location = 0
    with_image = 0
    for r in rows:
        payload = r["payload"]
        pt = problem_type_of(payload)
        if pt:
            by_problem_type[pt] = by_problem_type.get(pt, 0) + 1
        v = r["survey_version"]
        by_survey_version[v] = by_survey_version.get(v, 0) + 1
        if r["latitude"] is not None and r["longitude"] is not None:
            with_location += 1
        if extract_images(payload):
            with_image += 1
        if r["created_at"]:
            day = r["created_at"].date().isoformat()
            daily[day] = daily.get(day, 0) + 1

    total = len(rows)
    return {
        "total_users": user_count or 0,
        "total_completed_reports": total,
        "total_incomplete_reports": incomplete_count or 0,
        "by_problem_type": by_problem_type,
        "by_survey_version": by_survey_version,
        "with_location": with_location,
        "without_location": total - with_location,
        "with_image": with_image,
        "without_image": total - with_image,
        "daily": [{"date": d, "count": c} for d, c in sorted(daily.items())],
    }


async def get_available_dates(db: AsyncSession) -> dict:
    # ดึงวันที่ทั้งหมดที่มีการทำรายงาน (CompletedReport) เรียงใหม่→เก่า
    date_col = func.date(CompletedReport.created_at)
    query = select(date_col).distinct().order_by(date_col.desc())
    result = await db.execute(query)
    dates = [row[0].strftime("%Y-%m-%d") for row in result.all() if row[0]]
    return {"dates": dates}


async def list_completed(db, date, date_from, date_to, problem_type, page, limit) -> dict:
    query = select(
        CompletedReport.report_id,
        CompletedReport.lineuser_id,
        CompletedReport.survey_version,
        CompletedReport.payload,
        CompletedReport.created_at,
        ST_X(CompletedReport.location_data).label("longitude"),
        ST_Y(CompletedReport.location_data).label("latitude"),
    ).order_by(CompletedReport.created_at.desc())

    query = apply_date_range(query, CompletedReport.created_at, date, date_from, date_to)

    result = await db.execute(query)
    items = [serialize_completed(dict(row)) for row in result.mappings()]
    if problem_type:
        items = [i for i in items if i["problem_type"] == problem_type]
    return envelope(items, page, limit)


async def list_incomplete(db, date, page, limit) -> dict:
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

    query = apply_date_range(query, IncompleteReport.created_at, date, None, None)

    result = await db.execute(query)
    items = []
    for row in result.mappings():
        row = dict(row)
        question_id, question_text = resolve_drop_off_question(
            survey_manager,
            row["survey_version"],
            row["drop_off_route_id"],
            row["drop_off_step"],
        )
        items.append(serialize_incomplete(row, question_id, question_text))
    return envelope(items, page, limit)


async def list_form(db, date, page, limit) -> dict:
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

    query = apply_date_range(query, FormReport.created_at, date, None, None)

    result = await db.execute(query)
    items = [serialize_form(dict(row)) for row in result.mappings()]
    return envelope(items, page, limit)


async def list_broadcast(db, date, alert_type, page, limit) -> dict:
    # รายงานจาก broadcast แจ้งเตือนอากาศ (flood/heat/both) — พล็อตหมุดได้เหมือน report อื่น
    query = select(
        BroadcastReport.report_id,
        BroadcastReport.lineuser_id,
        BroadcastReport.alert_type,
        BroadcastReport.confirmed,
        BroadcastReport.community,
        BroadcastReport.note,
        BroadcastReport.image_path,
        BroadcastReport.created_at,
        ST_X(BroadcastReport.location_data).label("longitude"),
        ST_Y(BroadcastReport.location_data).label("latitude"),
    ).order_by(BroadcastReport.created_at.desc())

    query = apply_date_range(query, BroadcastReport.created_at, date, None, None)
    result = await db.execute(query)

    items = []
    for row in result.mappings():
        items.extend(serialize_broadcast(dict(row)))   # extend เพราะ both คืน 2 item
    if alert_type:
        items = [i for i in items if i["alert_type"] == alert_type]
    return envelope(items, page, limit)


async def get_report_detail(db, report_id: int) -> dict:
    query = select(
        CompletedReport.report_id,
        CompletedReport.lineuser_id,
        CompletedReport.survey_version,
        CompletedReport.payload,
        CompletedReport.created_at,
        ST_X(CompletedReport.location_data).label("longitude"),
        ST_Y(CompletedReport.location_data).label("latitude"),
    ).where(CompletedReport.report_id == report_id)

    result = await db.execute(query)
    report = result.mappings().first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return serialize_completed(dict(report))


# ── images ───────────────────────────────────────────────────────────────────
async def fetch_image_content(blob_api, image_id: str) -> bytes:
    """ดึง bytes รูปจาก LINE CDN.

    รูปถูก proxy สดจาก LINE ซึ่งลบทิ้งหลังผ่านไปสักพัก. ถ้ารูปหมดอายุ/หาไม่เจอ
    โยน HTTP 404 แทนที่จะปล่อยให้ exception หลุดไปเป็น 500.
    """
    try:
        return await blob_api.get_message_content(image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found or expired")


def survey_image_path(image_id: str) -> Optional[str]:
    """เส้นทางไฟล์รูป survey ที่เก็บถาวรแล้ว (uploads/survey/<id>.jpg) หรือ None."""
    return storage.local_file(f"survey/{image_id}.jpg")


async def fetch_line_image_bytes(image_id: str) -> bytes:
    """proxy สดจาก LINE CDN (สำหรับรูปเก่าที่ยังไม่ถูกเก็บถาวร)."""
    configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    async with AsyncApiClient(configuration) as api_client:
        blob_api = AsyncMessagingApiBlob(api_client)
        return await fetch_image_content(blob_api, image_id)


async def broadcast_image_path(db, report_id: int) -> str:
    # รูปจุดน้ำท่วมจาก broadcast report — เก็บถาวรใน uploads/broadcast/<id>.jpg (utils/storage)
    key = await db.scalar(
        select(BroadcastReport.image_path).where(BroadcastReport.report_id == report_id)
    )
    stored = storage.local_file(key)
    if not stored:
        raise HTTPException(status_code=404, detail="Image not found")
    return stored
