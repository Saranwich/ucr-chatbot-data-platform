import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import admin as admin_api
from app.clients import admin


class Record(dict):
    pass


class AdminApiTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(admin_api.router)
        self.client = TestClient(app)
        self.report_id = uuid4()
        self.session_id = uuid4()
        self.report = {
            "id": self.report_id,
            "created_at": datetime.now(timezone.utc),
            "status": "analyzed",
            "session_id": self.session_id,
            "title": "น้ำท่วม",
            "type": "flood",
            "threat": "high",
            "frequency": "often",
            "effect": "เดินทางไม่ได้",
            "is_has_image": True,
            "is_has_location": True,
            "locations": [],
            "images": [],
        }

    def test_report_list_contract_excludes_session_id(self):
        item = dict(self.report)
        item.pop("session_id")
        with patch.object(
            admin_api.admin_client,
            "list_reports",
            new=AsyncMock(return_value={"items": [item], "total": 1}),
        ) as call:
            response = self.client.get("/api/admin/reports?limit=12&offset=3&type=flood&days=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertNotIn("session_id", response.json()["items"][0])
        call.assert_awaited_once_with(12, 3, "flood", 7)

    def test_report_detail_includes_session_id_and_returns_404(self):
        with patch.object(
            admin_api.admin_client, "get_report", new=AsyncMock(return_value=self.report)
        ):
            response = self.client.get(f"/api/admin/reports/{self.report_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], str(self.session_id))

        with patch.object(admin_api.admin_client, "get_report", new=AsyncMock(return_value=None)):
            response = self.client.get(f"/api/admin/reports/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_query_validation(self):
        self.assertEqual(self.client.get("/api/admin/reports?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/admin/users?offset=-1").status_code, 422)
        self.assertEqual(self.client.get("/api/admin/reports?type=unknown").status_code, 422)
        self.assertEqual(self.client.get("/api/admin/statistics?days=0").status_code, 422)
        self.assertEqual(self.client.get("/api/admin/statistics?days=366").status_code, 422)

    def test_report_list_defaults_to_all_history(self):
        with patch.object(
            admin_api.admin_client,
            "list_reports",
            new=AsyncMock(return_value={"items": [], "total": 0}),
        ) as call:
            response = self.client.get("/api/admin/reports")
        self.assertEqual(response.status_code, 200)
        call.assert_awaited_once_with(50, 0, None, None)


class AdminClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_page_fetches_relations_in_batches(self):
        report_id = uuid4()
        location_id = uuid4()
        image_id = uuid4()
        report = Record(
            id=report_id,
            created_at=datetime.now(timezone.utc),
            status="analyzed",
            session_id=uuid4(),
            title="ไฟดับ",
            type="light",
            threat="mid",
            frequency="often",
            effect=None,
            is_has_image=True,
            is_has_location=True,
        )
        pool = AsyncMock()
        pool.fetchval.return_value = 1
        pool.fetch.side_effect = [
            [report],
            [Record(id=location_id, report_id=report_id, lat=1.2, lon=3.4, address=None)],
            [Record(id=image_id, report_id=report_id, desc="เสาไฟ")],
        ]
        with patch.object(admin.psql, "get_pool", return_value=pool):
            result = await admin.list_reports(20, 0, days=7)

        self.assertEqual(pool.fetch.await_count, 3)
        count_call = pool.fetchval.await_args_list[0]
        page_call = pool.fetch.await_args_list[0]
        self.assertEqual(count_call.args[1:], (None, 7))
        self.assertEqual(page_call.args[1:], (None, 7, 20, 0))
        self.assertIn("Asia/Bangkok", count_call.args[0])
        self.assertEqual(result["items"][0]["locations"][0]["id"], location_id)
        self.assertEqual(
            result["items"][0]["images"][0]["url"], f"/api/admin/images/{image_id}"
        )
        self.assertNotIn("session_id", result["items"][0])

    async def test_statistics_shape(self):
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            Record(users=2, sessions=3, images=5, locations=6),
            Record(total=4, with_image=3, with_location=2, with_both=1, without_media=0),
        ]
        pool.fetch.side_effect = [
            [Record(status="analyzed", count=2), Record(status="pending", count=1)],
            [Record(type="flood", count=3), Record(type="unclassified", count=1)],
            [Record(date=datetime(2026, 9, 14).date(), count=1), Record(date=datetime(2026, 9, 15).date(), count=3)],
        ]
        with patch.object(admin.psql, "get_pool", return_value=pool):
            result = await admin.get_statistics(2)
        self.assertEqual(result["period_days"], 2)
        self.assertEqual(result["sessions"], {"total": 3, "by_status": {"analyzed": 2, "pending": 1}})
        self.assertEqual(result["reports"]["by_type"], {"flood": 3, "unclassified": 1})
        self.assertEqual(result["reports"]["with_image"], 3)
        self.assertEqual(result["reports"]["with_location"], 2)
        self.assertEqual(result["reports"]["with_both"], 1)
        self.assertEqual(result["reports"]["without_media"], 0)
        self.assertEqual([row["count"] for row in result["reports"]["by_day"]], [1, 3])
        self.assertEqual(result["images"], {"total": 5})
        summary_sql = pool.fetchrow.await_args_list[1].args[0]
        self.assertIn("JOIN images image", summary_sql)
        self.assertIn("btrim(image.image_key) <> ''", summary_sql)
        self.assertIn("FROM locations loc", summary_sql)
        self.assertIn("loc.lat IS NOT NULL", summary_sql)
        self.assertIn("loc.lon IS NOT NULL", summary_sql)
        self.assertIn("Asia/Bangkok", summary_sql)
        self.assertIn("generate_series", pool.fetch.await_args_list[2].args[0])

    async def test_image_path_accepts_stored_key_and_rejects_escape(self):
        pool = AsyncMock()
        with tempfile.TemporaryDirectory() as directory:
            upload_dir = Path(directory)
            image = upload_dir / "safe.jpg"
            image.write_bytes(b"jpeg")
            with patch.object(admin, "UPLOAD_DIR", upload_dir), patch.object(
                admin.psql, "get_pool", return_value=pool
            ):
                pool.fetchval.return_value = "uploads/safe.jpg"
                self.assertEqual(await admin.get_image_path(uuid4()), image.resolve())
                pool.fetchval.return_value = "../outside.jpg"
                self.assertIsNone(await admin.get_image_path(uuid4()))
                pool.fetchval.return_value = "/etc/passwd"
                self.assertIsNone(await admin.get_image_path(uuid4()))


if __name__ == "__main__":
    unittest.main()
