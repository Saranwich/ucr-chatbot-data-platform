from datetime import datetime

from app.services.dashboard import serialize_report, envelope, with_offset


def _report_row(**over):
    row = {
        "report_id": 17,
        "lineuser_id": "U1",
        "conversation_id": 3,
        "community_id": 6,
        "source": "ai",
        "source_ref": None,
        "category": "น้ำท่วม/น้ำขัง",
        "notes": "น้ำท่วมซอย",
        "severity": "high",
        "title": "น้ำท่วม",
        "status": "completed",
        "is_complete": True,
        "extraction_confidence": 0.9,
        "payload": None,
        "created_at": datetime(2026, 6, 14, 3, 11, 10),
        "latitude": 14.07,
        "longitude": 100.6,
    }
    row.update(over)
    return row


def test_serialize_report_derives_fields():
    r = serialize_report(_report_row(), images=[{"image_id": 5, "image_url": "/api/dashboard/image/5"}])
    assert r["source"] == "ai"
    assert r["category"] == "น้ำท่วม/น้ำขัง"
    assert r["severity"] == "high"
    assert r["title"] == "น้ำท่วม"
    assert r["is_complete"] is True
    assert r["status"] == "completed"
    assert r["has_location"] is True
    assert r["has_image"] is True
    assert r["images"][0]["image_url"] == "/api/dashboard/image/5"
    assert r["extraction_confidence"] == 0.9


def test_serialize_report_flags_missing_location_and_image():
    r = serialize_report(_report_row(latitude=None, longitude=None))
    assert r["has_location"] is False
    assert r["has_image"] is False
    assert r["images"] == []


def test_created_at_gets_bangkok_offset():
    # naive Bangkok wall-clock → serialize เป็น ...+07:00
    r = serialize_report(_report_row())
    assert r["created_at"].isoformat() == "2026-06-14T03:11:10+07:00"
    assert with_offset(None) is None


def test_envelope_paginates():
    items = list(range(50))
    e = envelope(items, page=1, limit=20)
    assert e == {"items": list(range(20)), "total": 50, "page": 1, "limit": 20}
    assert envelope(items, page=3, limit=20)["items"] == list(range(40, 50))
