from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from app.clients import psql
from app.core.config import UPLOAD_DIR

REPORT_COLUMNS = """
    id, created_at, status, session_id, title, type, threat, frequency,
    effect, is_has_image, is_has_location
"""


def _image_url(image_id: UUID) -> str:
    return f"/api/admin/images/{image_id}"


async def _attach_relations(reports: list[dict]) -> list[dict]:
    if not reports:
        return reports

    report_ids = [report["id"] for report in reports]
    pool = psql.get_pool()
    location_rows = await pool.fetch(
        """
        SELECT id, report_id, lat, lon, address
        FROM locations
        WHERE report_id = ANY($1::uuid[])
        ORDER BY created_at, id
        """,
        report_ids,
    )
    image_rows = await pool.fetch(
        """
        SELECT image.id, relation.report_id, image."desc"
        FROM report_images AS relation
        JOIN images AS image ON image.id = relation.image_id
        WHERE relation.report_id = ANY($1::uuid[])
        ORDER BY image.created_at, image.id
        """,
        report_ids,
    )

    by_id = {report["id"]: report for report in reports}
    for report in reports:
        report["locations"] = []
        report["images"] = []
    for row in location_rows:
        location = dict(row)
        report_id = location.pop("report_id")
        by_id[report_id]["locations"].append(location)
    for row in image_rows:
        image = dict(row)
        report_id = image.pop("report_id")
        image["url"] = _image_url(image["id"])
        by_id[report_id]["images"].append(image)
    return reports


async def list_reports(
    limit: int, offset: int, report_type: str | None = None, days: int | None = None
) -> dict:
    pool = psql.get_pool()
    period_filter = """
        ($2::int IS NULL OR created_at >= (
            ((now() AT TIME ZONE 'Asia/Bangkok')::date - ($2::int - 1))
            AT TIME ZONE 'Asia/Bangkok'
        ))
    """
    total = await pool.fetchval(
        f"SELECT count(*) FROM reports WHERE ($1::text IS NULL OR type = $1) AND {period_filter}",
        report_type,
        days,
    )
    rows = await pool.fetch(
        f"""SELECT {REPORT_COLUMNS} FROM reports
            WHERE ($1::text IS NULL OR type = $1) AND {period_filter}
            ORDER BY created_at DESC, id LIMIT $3 OFFSET $4""",
        report_type,
        days,
        limit,
        offset,
    )
    reports = await _attach_relations([dict(row) for row in rows])
    for report in reports:
        report.pop("session_id")
    return {"items": reports, "total": total}


async def get_report(report_id: UUID) -> dict | None:
    row = await psql.get_pool().fetchrow(
        f"SELECT {REPORT_COLUMNS} FROM reports WHERE id = $1", report_id
    )
    if row is None:
        return None
    return (await _attach_relations([dict(row)]))[0]


async def get_statistics(days: int = 30) -> dict:
    pool = psql.get_pool()
    totals = await pool.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM users) AS users,
            (SELECT count(*) FROM sessions) AS sessions,
            (SELECT count(*) FROM images) AS images,
            (SELECT count(*) FROM locations) AS locations
        """
    )
    session_rows = await pool.fetch(
        "SELECT status, count(*) AS count FROM sessions GROUP BY status ORDER BY status"
    )
    report_summary = await pool.fetchrow(
        """
        WITH period_reports AS (
            SELECT id
            FROM reports
            WHERE created_at >= (
                ((now() AT TIME ZONE 'Asia/Bangkok')::date - ($1::int - 1))
                AT TIME ZONE 'Asia/Bangkok'
            )
        ), media AS (
            SELECT report.id,
                   EXISTS (
                       SELECT 1
                       FROM report_images ri
                       JOIN images image ON image.id = ri.image_id
                       WHERE ri.report_id = report.id
                         AND image.image_key IS NOT NULL
                         AND btrim(image.image_key) <> ''
                   ) AS has_image,
                   EXISTS (
                       SELECT 1 FROM locations loc
                       WHERE loc.report_id = report.id
                         AND loc.lat IS NOT NULL
                         AND loc.lon IS NOT NULL
                   ) AS has_location
            FROM period_reports report
        )
        SELECT count(*) AS total,
               count(*) FILTER (WHERE has_image) AS with_image,
               count(*) FILTER (WHERE has_location) AS with_location,
               count(*) FILTER (WHERE has_image AND has_location) AS with_both,
               count(*) FILTER (WHERE NOT has_image AND NOT has_location) AS without_media
        FROM media
        """,
        days,
    )
    report_rows = await pool.fetch(
        """
        SELECT coalesce(type, 'unclassified') AS type, count(*) AS count
        FROM reports
        WHERE created_at >= (
            ((now() AT TIME ZONE 'Asia/Bangkok')::date - ($1::int - 1))
            AT TIME ZONE 'Asia/Bangkok'
        )
        GROUP BY coalesce(type, 'unclassified')
        ORDER BY type
        """,
        days,
    )
    daily_rows = await pool.fetch(
        """
        WITH days AS (
            SELECT generate_series(
                (now() AT TIME ZONE 'Asia/Bangkok')::date - ($1::int - 1),
                (now() AT TIME ZONE 'Asia/Bangkok')::date,
                interval '1 day'
            )::date AS date
        ), report_counts AS (
            SELECT (created_at AT TIME ZONE 'Asia/Bangkok')::date AS date, count(*) AS count
            FROM reports
            WHERE created_at >= (
                ((now() AT TIME ZONE 'Asia/Bangkok')::date - ($1::int - 1))
                AT TIME ZONE 'Asia/Bangkok'
            )
            GROUP BY (created_at AT TIME ZONE 'Asia/Bangkok')::date
        )
        SELECT days.date, coalesce(report_counts.count, 0) AS count
        FROM days LEFT JOIN report_counts USING (date)
        ORDER BY days.date
        """,
        days,
    )
    return {
        "period_days": days,
        "users": {"total": totals["users"]},
        "sessions": {
            "total": totals["sessions"],
            "by_status": {row["status"]: row["count"] for row in session_rows},
        },
        "reports": {
            "total": report_summary["total"],
            "by_type": {row["type"]: row["count"] for row in report_rows},
            "by_day": [dict(row) for row in daily_rows],
            "with_image": report_summary["with_image"],
            "with_location": report_summary["with_location"],
            "with_both": report_summary["with_both"],
            "without_media": report_summary["without_media"],
        },
        "images": {"total": totals["images"]},
        "locations": {"total": totals["locations"]},
    }


async def list_users(limit: int, offset: int) -> dict:
    pool = psql.get_pool()
    total = await pool.fetchval("SELECT count(*) FROM users")
    rows = await pool.fetch(
        "SELECT id, line_user_id, name FROM users ORDER BY name NULLS LAST, id LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return {"items": [dict(row) for row in rows], "total": total}


async def get_image_path(image_id: UUID) -> Path | None:
    image_key = await psql.get_pool().fetchval(
        "SELECT image_key FROM images WHERE id = $1", image_id
    )
    if not image_key:
        return None

    key = Path(image_key)
    if key.is_absolute():
        return None
    parts: Iterable[str] = key.parts
    if key.parts and key.parts[0] == "uploads":
        parts = key.parts[1:]
    candidate = UPLOAD_DIR.joinpath(*parts).resolve()
    upload_root = UPLOAD_DIR.resolve()
    try:
        candidate.relative_to(upload_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
