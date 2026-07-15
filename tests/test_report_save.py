"""report.save() maps an extracted report → a reports-table INSERT (async seam).

No live DB: a fake AsyncSession captures the Report row so we can assert the
column mapping (category string → category_id FK, location → location_text, the
producer-set source/status/is_complete pass-through).
"""
import asyncio

from app.services import report


class FakeSession:
    """Stand-in for database_manager.get_session() — captures the added rows."""
    def __init__(self, category_id=7):
        self.added = []
        self._category_id = category_id

    @property
    def captured(self):
        return self.added[0] if self.added else None   # แถว Report มาก่อนเสมอ

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def scalar(self, stmt):
        return self._category_id          # categories.value → id lookup

    async def get(self, model, pk):
        return None                        # no user row → community_id stays null

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self.added:
            self.added[0].report_id = 42   # flush ให้ report_id ก่อน commit (แถวรูปใช้ FK)

    async def commit(self):
        pass

    async def refresh(self, obj):
        obj.report_id = 42


def test_save_maps_report_to_reports_row(monkeypatch):
    fake = FakeSession(category_id=7)
    monkeypatch.setattr(report, "get_session", lambda: fake)

    rid = asyncio.run(report.save("U1", {
        "category": "ไฟฟ้าสาธารณะ", "notes": "ถนนมืด", "location": "ซอย 5",
        "severity": "high", "title": "ไฟดับ",
        "source": "ai", "status": "completed", "is_complete": True,
    }))

    row = fake.captured
    assert rid == 42
    assert row.lineuser_id == "U1"
    assert row.category_id == 7                 # category string resolved to FK
    assert row.location_text == "ซอย 5"          # tool arg 'location' → column location_text
    assert row.notes == "ถนนมืด"
    assert row.severity == "high"
    assert row.title == "ไฟดับ"
    assert row.source == "ai"
    assert row.status == "completed"
    assert row.is_complete is True
    assert row.community_id is None              # no user row → null


def test_save_leaves_category_null_when_unknown(monkeypatch):
    # unknown category (drift) → scalar lookup returns None → category_id null, no crash
    fake = FakeSession(category_id=None)
    monkeypatch.setattr(report, "get_session", lambda: fake)

    asyncio.run(report.save("U2", {"category": "ไม่มีในลิสต์", "notes": "x",
                                    "source": "ai", "status": "completed", "is_complete": True}))
    assert fake.captured.category_id is None


def test_save_attaches_location_and_images(monkeypatch):
    # lat/lon → PostGIS WKT ใน location_data; image_keys → แถว report_images ชี้ report_id
    fake = FakeSession()
    monkeypatch.setattr(report, "get_session", lambda: fake)

    asyncio.run(report.save("U3", {
        "category": "ไฟฟ้าสาธารณะ", "notes": "x",
        "source": "ai", "status": "completed", "is_complete": True,
        "lat": 13.87, "lon": 100.57,
        "image_keys": ["reports/a.jpg", "reports/b.jpg"],
    }))

    assert fake.captured.location_data == "SRID=4326;POINT(100.57 13.87)"  # (lon lat)!
    image_rows = fake.added[1:]
    assert [r.image_key for r in image_rows] == ["reports/a.jpg", "reports/b.jpg"]
    assert all(r.report_id == 42 for r in image_rows)
