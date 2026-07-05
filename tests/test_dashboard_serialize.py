from datetime import datetime

from app.services.dashboard import serialize_completed, serialize_form, envelope, with_offset


def _completed_row(**over):
    row = {
        "report_id": 17,
        "lineuser_id": "U1",
        "survey_version": "fdg140626",
        "payload": {
            "q_start": "น้ำท่วม/น้ำขัง",
            "q_photo": {"image_id": "img1"},
        },
        "created_at": datetime(2026, 6, 14, 3, 11, 10),
        "latitude": 14.07,
        "longitude": 100.6,
    }
    row.update(over)
    return row


def test_serialize_completed_derives_fields():
    r = serialize_completed(_completed_row())
    assert r["problem_type"] == "น้ำท่วม/น้ำขัง"
    assert r["source"] == "survey"
    assert r["is_complete"] is True
    assert r["status"] == "completed"
    assert r["has_location"] is True
    assert r["has_image"] is True
    assert r["images"][0]["image_url"] == "/api/dashboard/image/img1"


def test_serialize_completed_flags_missing_location_and_image():
    r = serialize_completed(_completed_row(payload={"q_start": "อากาศร้อน"}, latitude=None, longitude=None))
    assert r["has_location"] is False
    assert r["has_image"] is False
    assert r["images"] == []


def test_created_at_gets_bangkok_offset():
    # naive Bangkok wall-clock → serialize เป็น ...+07:00
    r = serialize_completed(_completed_row())
    assert r["created_at"].isoformat() == "2026-06-14T03:11:10+07:00"
    assert with_offset(None) is None


def test_serialize_form_shape():
    r = serialize_form({
        "report_id": 29, "lineuser_id": "U2", "category": "จุดเสี่ยง",
        "description": "d", "status": "new", "image_path": "reports/x.jpg",
        "created_at": datetime(2026, 6, 26, 9, 30), "latitude": 13.8, "longitude": 100.5,
    })
    assert r["source"] == "form_report"
    assert r["has_image"] is True
    assert r["image_url"] == "/api/form-reports/29/image"


def test_envelope_paginates():
    items = list(range(50))
    e = envelope(items, page=1, limit=20)
    assert e == {"items": list(range(20)), "total": 50, "page": 1, "limit": 20}
    assert envelope(items, page=3, limit=20)["items"] == list(range(40, 50))
