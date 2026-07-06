"""One-shot migration: the 4 legacy tables → the central `reports` table.

Run this ONCE before dropping the legacy tables (Alembic 0002). It migrates:
  - completed_reports + incomplete_reports (V1 survey) → reports(source='survey',
    source_ref=<survey_version>): each raw payload is run through the SAME
    services/llm record_complaint extraction (category enum-locked); the raw answers
    are kept verbatim in reports.payload as the safety net.
  - form_reports      → reports(source='form_report')            — direct column map.
  - broadcast_reports → reports(source='broadcast', source_ref=alert_type) — direct map.
Geometry + images are carried across (report_images). Every legacy table is archived
verbatim through the storage seam (uploads/archive/<table>.json) before migrating.

# ponytail: reads the legacy tables via RAW SQL + a to_regclass existence guard —
# NOT the ORM models — so this script keeps working after M4 deletes those models,
# and cleanly skips a table that has already been dropped. Only the write-side
# (Report/ReportImage) uses the live ORM.
# ponytail: best-effort survey extraction — no GEMINI key / a failed call leaves the
# 4 tool fields null (#81 serves null) and the raw payload + archive blob are the
# safety net, not a correctness gate.
# ponytail: idempotent via a `_backfill` provenance marker in reports.payload — a
# legacy (table, report_id) already carried in some reports.payload is skipped, so
# re-runs don't duplicate. No destructive truncate.
"""
import asyncio
import json

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text

from app.database.database_manager import get_session
from app.models import Report, ReportImage
from app.services import report as report_service, llm
from app.services.ai_tool import RECORD_COMPLAINT
from app.handlers.broadcast_flow_handler import _BROADCAST_CATEGORY_VALUE
from app.utils import storage

_BACKFILL_SYSTEM = (
    "ต่อไปนี้คือคำตอบจากแบบสำรวจชุมชนเวอร์ชันเก่า (survey) ของผู้ใช้ 1 คน "
    "ช่วยสรุปเป็นปัญหาชุมชน 1 เรื่องแล้วเรียกเครื่องมือ record_complaint เพียงครั้งเดียว "
    "เลือก category จากลิสต์ที่กำหนดเท่านั้น ถ้าข้อมูลเดิมไม่พอสำหรับช่องไหนให้เว้นว่าง"
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _as_dict(payload) -> dict:
    """asyncpg hands a raw-SQL json/jsonb column back as a str — normalise to dict."""
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except (ValueError, TypeError):
            return {}
    return payload or {}


def _geom(wkt):
    """ST_AsText() string → a Geometry the ORM can INSERT (None-safe)."""
    return WKTElement(wkt, srid=4326) if wkt else None


async def _table_exists(db, table: str) -> bool:
    return (await db.scalar(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})) is not None


async def _read(db, table: str, columns: str) -> list[dict]:
    """Raw SELECT of a legacy table (geometry as ST_AsText 'wkt'); [] if it's gone."""
    if not await _table_exists(db, table):
        print(f"  {table}: not present — skipping")
        return []
    rows = (await db.execute(text(f"SELECT {columns} FROM {table}"))).mappings().all()
    return [dict(r) for r in rows]


def _archive(table: str, rows: list[dict]) -> None:
    """Dump the raw legacy rows verbatim via the storage seam (backup net)."""
    blob = json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")
    key = storage.save_blob(f"archive/{table}.json", blob)
    print(f"  archived {len(rows)} row(s) → {key}")


async def _seen(db) -> set:
    """(table, report_id) pairs already migrated — read from reports.payload markers."""
    payloads = (await db.execute(
        select(Report.payload).where(Report.payload.isnot(None))
    )).scalars().all()
    out = set()
    for p in payloads:
        ref = (p or {}).get("_backfill")
        if ref:
            out.add((ref["table"], ref["report_id"]))
    return out


async def _extract(payload: dict) -> dict:
    """Best-effort record_complaint extraction from a raw survey payload."""
    captured: dict = {}

    def handler(name, args):
        if name == "record_complaint" and not captured:
            captured.update(args)

    try:
        await llm.chat(
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            system=_BACKFILL_SYSTEM,
            tools=[RECORD_COMPLAINT],
            tool_handler=handler,
        )
    except Exception as e:  # no key / network / model hiccup — degrade to raw-only
        print(f"  extraction skipped ({type(e).__name__}); keeping raw payload only")
    return captured


# ── per-source migration ──────────────────────────────────────────────────────
async def _migrate_surveys(db, seen: set) -> int:
    inserted = 0
    for table, is_complete, default_status, cols in (
        ("completed_reports", True, "completed",
         "report_id, lineuser_id, survey_version, payload, created_at, "
         "ST_AsText(location_data) AS wkt"),
        ("incomplete_reports", False, "timeout",
         "report_id, lineuser_id, survey_version, payload, status, created_at, "
         "drop_off_route_id, drop_off_step, ST_AsText(location_data) AS wkt"),
    ):
        rows = await _read(db, table, cols)
        if rows:
            _archive(table, rows)
        for r in rows:
            ref = (table, r["report_id"])
            if ref in seen:
                continue
            raw = _as_dict(r["payload"])
            extracted = await _extract(raw)
            db.add(Report(
                lineuser_id=r["lineuser_id"],
                community_id=await report_service.community_id_for(db, r["lineuser_id"]),
                source="survey",
                source_ref=r["survey_version"],
                category_id=await report_service.category_id_for(db, extracted.get("category")),
                notes=extracted.get("notes"),
                severity=extracted.get("severity"),
                title=extracted.get("title"),
                status=r.get("status") or default_status,
                is_complete=is_complete,
                location_text=extracted.get("location"),
                location_data=_geom(r["wkt"]),
                payload={**raw, "_backfill": {"table": table, "report_id": r["report_id"]}},
                created_at=r["created_at"],
            ))
            inserted += 1
    return inserted


async def _migrate_form(db, seen: set) -> int:
    rows = await _read(db, "form_reports",
                       "report_id, lineuser_id, category, description, status, "
                       "image_path, created_at, ST_AsText(location_data) AS wkt")
    if rows:
        _archive("form_reports", rows)
    inserted = 0
    for r in rows:
        ref = ("form_reports", r["report_id"])
        if ref in seen:
            continue
        rep = Report(
            lineuser_id=r["lineuser_id"],
            community_id=await report_service.community_id_for(db, r["lineuser_id"]),
            source="form_report",
            category_id=await report_service.category_id_for(db, r["category"]),
            notes=r["description"],
            status=r["status"] or "new",
            is_complete=True,
            location_data=_geom(r["wkt"]),
            payload={"_backfill": {"table": "form_reports", "report_id": r["report_id"]}},
            created_at=r["created_at"],
        )
        db.add(rep)
        await db.flush()
        if r["image_path"]:
            db.add(ReportImage(report_id=rep.report_id, image_key=r["image_path"]))
        inserted += 1
    return inserted


async def _migrate_broadcast(db, seen: set) -> int:
    rows = await _read(db, "broadcast_reports",
                       "report_id, lineuser_id, alert_type, confirmed, note, community, "
                       "image_path, status, created_at, ST_AsText(location_data) AS wkt")
    if rows:
        _archive("broadcast_reports", rows)
    inserted = 0
    for r in rows:
        ref = ("broadcast_reports", r["report_id"])
        if ref in seen:
            continue
        confirmed = bool(r["confirmed"])
        rep = Report(
            lineuser_id=r["lineuser_id"],
            community_id=await report_service.community_id_for(db, r["lineuser_id"]),
            source="broadcast",
            source_ref=r["alert_type"],
            category_id=await report_service.category_id_for(
                db, _BROADCAST_CATEGORY_VALUE.get(r["alert_type"])),
            notes=r["note"],
            status="completed" if confirmed else "cancelled",
            is_complete=confirmed,
            location_data=_geom(r["wkt"]),
            payload={"_backfill": {"table": "broadcast_reports", "report_id": r["report_id"]}},
            created_at=r["created_at"],
        )
        db.add(rep)
        await db.flush()
        if r["image_path"]:
            db.add(ReportImage(report_id=rep.report_id, image_key=r["image_path"]))
        inserted += 1
    return inserted


async def run() -> dict:
    """Archive + migrate every legacy table. Returns per-source insert counts."""
    async with get_session() as db:
        seen = await _seen(db)
        counts = {
            "survey": await _migrate_surveys(db, seen),
            "form_report": await _migrate_form(db, seen),
            "broadcast": await _migrate_broadcast(db, seen),
        }
        await db.commit()
    print(f"backfill done — inserted {counts}")
    return counts


if __name__ == "__main__":
    asyncio.run(run())
