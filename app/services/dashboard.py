"""Dashboard data layer — reads the single central `reports` table (+ report_images).

V2 cutover (#81): every channel (ai / form_report / broadcast / survey-backfill)
lands one `reports` row distinguished by `source`, so the dashboard reads ONE table
and serializes ONE unified shape. Routes in routes/dashboard.py stay thin.

# ponytail: these raise HTTPException (400/404) directly — fine for one small app;
# not worth a separate error-translation layer.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y

from app.models import User, Report, ReportImage, Category
from app.utils import storage

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
    """ดึงรูปทั้งหมดออกมาจาก payload JSONB (ของเก่า survey backfill เก็บรูปใน payload).

    รูปถูกเก็บใน payload ใต้ key ของคำถาม (ชื่อต่างกันทุก survey เช่น q_photo) เป็น
    dict {image_id, image_url}. ฟังก์ชันนี้สแกนหาทุกตัวที่เป็น dict มี image_id.
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


def serialize_report(row: dict, images: Optional[list] = None) -> dict:
    """ปั้น 1 แถว reports → shape เดียวตาม contract #81 (null แทน omit).

    lat/lon มาจาก ST_X/ST_Y (longitude/latitude), category = categories.value (join),
    images = แถวใน report_images (serve ผ่าน /api/dashboard/image/{image_id}).
    """
    images = images or []
    lat, lon = row["latitude"], row["longitude"]
    return {
        "report_id": row["report_id"],
        "lineuser_id": row["lineuser_id"],
        "conversation_id": row["conversation_id"],
        "community_id": row["community_id"],
        "source": row["source"],
        "source_ref": row["source_ref"],
        "category": row["category"],
        "notes": row["notes"],
        "severity": row["severity"],
        "title": row["title"],
        "status": row["status"],
        "is_complete": bool(row["is_complete"]),
        "latitude": lat,
        "longitude": lon,
        "has_location": lat is not None and lon is not None,
        "extraction_confidence": row["extraction_confidence"],
        "images": images,
        "has_image": bool(images),
        "payload": row["payload"],
        "created_at": with_offset(row["created_at"]),
    }


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


# ── unified reports query ─────────────────────────────────────────────────────
def _base_report_query():
    """reports LEFT JOIN categories, with lat/lon via ST_X/ST_Y — the #81 columns."""
    return select(
        Report.report_id, Report.lineuser_id, Report.conversation_id,
        Report.community_id, Report.source, Report.source_ref,
        Category.value.label("category"), Report.notes, Report.severity,
        Report.title, Report.status, Report.is_complete,
        Report.extraction_confidence, Report.payload, Report.created_at,
        ST_X(Report.location_data).label("longitude"),
        ST_Y(Report.location_data).label("latitude"),
    ).select_from(Report).join(Category, Report.category_id == Category.id, isouter=True)


async def _images_for(db: AsyncSession, report_ids: list) -> dict:
    """report_id → [{image_id, image_url}]. One extra query, grouped in Python.

    ponytail: data ยังเล็ก — 1 query แล้ว group ในโค้ด (ไม่ต้อง join/aggregate ใน SQL).
    """
    if not report_ids:
        return {}
    rows = (await db.execute(
        select(ReportImage.report_id, ReportImage.image_id)
        .where(ReportImage.report_id.in_(report_ids))
    )).all()
    out: dict = {}
    for rid, iid in rows:
        out.setdefault(rid, []).append({"image_id": iid, "image_url": f"/api/dashboard/image/{iid}"})
    return out


async def _serialize_rows(db: AsyncSession, query) -> list:
    rows = [dict(r) for r in (await db.execute(query)).mappings()]
    imgs = await _images_for(db, [r["report_id"] for r in rows])
    return [serialize_report(r, imgs.get(r["report_id"], [])) for r in rows]


# ── queries (each takes a db session, returns dashboard-ready data) ───────────
async def get_stats(db: AsyncSession) -> dict:
    user_count = await db.scalar(select(func.count(User.lineuser_id)))
    rows = (await db.execute(
        select(
            Report.report_id, Report.source, Report.status, Report.is_complete,
            Category.value.label("category"), Report.created_at,
            ST_X(Report.location_data).label("longitude"),
            ST_Y(Report.location_data).label("latitude"),
        ).select_from(Report).join(Category, Report.category_id == Category.id, isouter=True)
    )).mappings().all()
    img_report_ids = set((await db.execute(select(ReportImage.report_id).distinct())).scalars().all())

    by_source: dict = {}
    by_category: dict = {}
    by_status: dict = {}
    daily: dict = {}
    with_location = 0
    with_image = 0
    for r in rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        if r["category"]:
            by_category[r["category"]] = by_category.get(r["category"], 0) + 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        if r["latitude"] is not None and r["longitude"] is not None:
            with_location += 1
        if r["report_id"] in img_report_ids:
            with_image += 1
        if r["created_at"]:
            day = r["created_at"].date().isoformat()
            daily[day] = daily.get(day, 0) + 1

    total = len(rows)
    return {
        "total_users": user_count or 0,
        "total_reports": total,
        "by_source": by_source,
        "by_category": by_category,
        "by_status": by_status,
        "with_location": with_location,
        "without_location": total - with_location,
        "with_image": with_image,
        "without_image": total - with_image,
        "daily": [{"date": d, "count": c} for d, c in sorted(daily.items())],
    }


async def get_available_dates(db: AsyncSession) -> dict:
    date_col = func.date(Report.created_at)
    query = select(date_col).distinct().order_by(date_col.desc())
    result = await db.execute(query)
    dates = [row[0].strftime("%Y-%m-%d") for row in result.all() if row[0]]
    return {"dates": dates}


async def list_completed(db, date, date_from, date_to, problem_type, page, limit) -> dict:
    # /reports = unified feed ของทุก source (source field แยกช่องทาง). problem_type = category.
    query = _base_report_query()
    query = apply_date_range(query, Report.created_at, date, date_from, date_to)
    if problem_type:
        query = query.where(Category.value == problem_type)
    query = query.order_by(Report.created_at.desc())
    return envelope(await _serialize_rows(db, query), page, limit)


async def list_incomplete(db, date, page, limit) -> dict:
    # รายงานที่ยังไม่ครบ (survey backfill drop-off = is_complete false)
    query = _base_report_query().where(Report.is_complete.is_(False))
    query = apply_date_range(query, Report.created_at, date, None, None)
    query = query.order_by(Report.created_at.desc())
    return envelope(await _serialize_rows(db, query), page, limit)


async def list_form(db, date, page, limit) -> dict:
    query = _base_report_query().where(Report.source == "form_report")
    query = apply_date_range(query, Report.created_at, date, None, None)
    query = query.order_by(Report.created_at.desc())
    return envelope(await _serialize_rows(db, query), page, limit)


async def list_broadcast(db, date, alert_type, page, limit) -> dict:
    # broadcast: alert_type (flood/heat/both) เก็บใน source_ref
    query = _base_report_query().where(Report.source == "broadcast")
    query = apply_date_range(query, Report.created_at, date, None, None)
    if alert_type:
        query = query.where(Report.source_ref == alert_type)
    query = query.order_by(Report.created_at.desc())
    return envelope(await _serialize_rows(db, query), page, limit)


async def get_report_detail(db, report_id: int) -> dict:
    query = _base_report_query().where(Report.report_id == report_id)
    items = await _serialize_rows(db, query)
    if not items:
        raise HTTPException(status_code=404, detail="Report not found")
    return items[0]


# ── images ───────────────────────────────────────────────────────────────────
async def fetch_image_content(blob_api, image_id: str) -> bytes:
    """ดึง bytes รูปจาก LINE CDN (seam เดิม — เก็บไว้เผื่อ proxy รูปที่ยังไม่ persist).

    ถ้ารูปหมดอายุ/หาไม่เจอ โยน HTTP 404 แทนที่จะปล่อยเป็น 500.
    """
    try:
        return await blob_api.get_message_content(image_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found or expired")


async def report_image_path(db, image_id: int) -> str:
    """local path ของรูปใน report_images (serve store-first). 404 ถ้าไม่มี/ไฟล์หาย."""
    key = await db.scalar(select(ReportImage.image_key).where(ReportImage.image_id == image_id))
    stored = storage.local_file(key)
    if not stored:
        raise HTTPException(status_code=404, detail="Image not found")
    return stored
