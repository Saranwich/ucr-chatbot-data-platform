import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dashboard as dashboard_api
from app.clients import psql
from app.services import dashboard


class Record(dict):
    pass


class DashboardApiTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(dashboard_api.router)
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
            dashboard_api.service,
            "list_reports",
            new=AsyncMock(return_value={"items": [item], "total": 1}),
        ) as call:
            response = self.client.get("/api/dashboard/reports?limit=12&offset=3&type=flood&days=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertNotIn("session_id", response.json()["items"][0])
        call.assert_awaited_once_with(12, 3, "flood", 7)

    def test_report_detail_includes_session_id_and_returns_404(self):
        with patch.object(
            dashboard_api.service, "get_report", new=AsyncMock(return_value=self.report)
        ):
            response = self.client.get(f"/api/dashboard/reports/{self.report_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], str(self.session_id))

        with patch.object(dashboard_api.service, "get_report", new=AsyncMock(return_value=None)):
            response = self.client.get(f"/api/dashboard/reports/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_query_validation(self):
        self.assertEqual(self.client.get("/api/dashboard/reports?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/dashboard/users?offset=-1").status_code, 422)
        self.assertEqual(self.client.get("/api/dashboard/reports?type=unknown").status_code, 422)
        self.assertEqual(self.client.get("/api/dashboard/statistics?days=0").status_code, 422)
        self.assertEqual(self.client.get("/api/dashboard/statistics?days=366").status_code, 422)

    def test_report_list_defaults_to_all_history(self):
        with patch.object(
            dashboard_api.service,
            "list_reports",
            new=AsyncMock(return_value={"items": [], "total": 0}),
        ) as call:
            response = self.client.get("/api/dashboard/reports")
        self.assertEqual(response.status_code, 200)
        call.assert_awaited_once_with(50, 0, None, None)


class DashboardServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_page_attaches_media_and_hides_session_id(self):
        report_id = uuid4()
        location_id = uuid4()
        image_id = uuid4()
        report = {
            "id": report_id,
            "created_at": datetime.now(timezone.utc),
            "status": "analyzed",
            "session_id": uuid4(),
            "title": "ไฟดับ",
            "type": "light",
            "threat": "mid",
            "frequency": "often",
            "effect": None,
            "is_has_image": True,
            "is_has_location": True,
        }
        with (
            patch.object(dashboard.psql, "count_reports", new=AsyncMock(return_value=1)),
            patch.object(dashboard.psql, "get_reports", new=AsyncMock(return_value=[report])) as page,
            patch.object(
                dashboard.psql,
                "get_locations_of_reports",
                new=AsyncMock(return_value=[
                    {"id": location_id, "report_id": report_id, "lat": 1.2, "lon": 3.4, "address": None}
                ]),
            ) as locations,
            patch.object(
                dashboard.psql,
                "get_images_of_reports",
                new=AsyncMock(return_value=[
                    {"id": image_id, "report_id": report_id, "desc": "เสาไฟ"}
                ]),
            ) as images,
        ):
            result = await dashboard.list_reports(20, 0, days=7)

        page.assert_awaited_once_with(20, 0, None, 7)
        locations.assert_awaited_once_with([report_id])
        images.assert_awaited_once_with([report_id])
        self.assertEqual(result["items"][0]["locations"][0]["id"], location_id)
        self.assertEqual(
            result["items"][0]["images"][0]["url"], f"/api/dashboard/images/{image_id}"
        )
        self.assertNotIn("session_id", result["items"][0])

    async def test_empty_page_does_not_query_media(self):
        with (
            patch.object(dashboard.psql, "count_reports", new=AsyncMock(return_value=0)),
            patch.object(dashboard.psql, "get_reports", new=AsyncMock(return_value=[])),
            patch.object(dashboard.psql, "get_locations_of_reports", new=AsyncMock()) as locations,
            patch.object(dashboard.psql, "get_images_of_reports", new=AsyncMock()) as images,
        ):
            result = await dashboard.list_reports(20, 0)
        self.assertEqual(result, {"items": [], "total": 0})
        locations.assert_not_awaited()
        images.assert_not_awaited()

    async def test_statistics_shape(self):
        with (
            patch.object(
                dashboard.psql,
                "get_entity_totals",
                new=AsyncMock(return_value={"users": 2, "sessions": 3, "images": 5, "locations": 6}),
            ),
            patch.object(
                dashboard.psql,
                "get_session_status_counts",
                new=AsyncMock(return_value=[
                    {"status": "analyzed", "count": 2}, {"status": "pending", "count": 1}
                ]),
            ),
            patch.object(
                dashboard.psql,
                "get_report_media_coverage",
                new=AsyncMock(return_value={
                    "total": 4, "with_image": 3, "with_location": 2, "with_both": 1, "without_media": 0
                }),
            ),
            patch.object(
                dashboard.psql,
                "get_report_type_counts",
                new=AsyncMock(return_value=[
                    {"type": "flood", "count": 3}, {"type": "unclassified", "count": 1}
                ]),
            ),
            patch.object(
                dashboard.psql,
                "get_report_daily_counts",
                new=AsyncMock(return_value=[
                    {"date": datetime(2026, 9, 14).date(), "count": 1},
                    {"date": datetime(2026, 9, 15).date(), "count": 3},
                ]),
            ),
        ):
            result = await dashboard.get_statistics(2)

        self.assertEqual(result["period_days"], 2)
        self.assertEqual(result["sessions"], {"total": 3, "by_status": {"analyzed": 2, "pending": 1}})
        self.assertEqual(result["reports"]["by_type"], {"flood": 3, "unclassified": 1})
        self.assertEqual(result["reports"]["with_image"], 3)
        self.assertEqual(result["reports"]["with_location"], 2)
        self.assertEqual(result["reports"]["with_both"], 1)
        self.assertEqual(result["reports"]["without_media"], 0)
        self.assertEqual([row["count"] for row in result["reports"]["by_day"]], [1, 3])
        self.assertEqual(result["images"], {"total": 5})

    async def test_image_path_accepts_stored_key_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            upload_dir = Path(directory)
            image = upload_dir / "safe.jpg"
            image.write_bytes(b"jpeg")
            key = AsyncMock()
            with (
                patch.object(dashboard, "UPLOAD_DIR", upload_dir),
                patch.object(dashboard.psql, "get_image_key", new=key),
            ):
                key.return_value = "uploads/safe.jpg"
                self.assertEqual(await dashboard.get_image_path(uuid4()), image.resolve())
                key.return_value = "../outside.jpg"
                self.assertIsNone(await dashboard.get_image_path(uuid4()))
                key.return_value = "/etc/passwd"
                self.assertIsNone(await dashboard.get_image_path(uuid4()))


class DashboardQueryTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_page_counts_days_in_bangkok_time(self):
        pool = AsyncMock()
        pool.fetchval.return_value = 1
        pool.fetch.return_value = []
        with patch.object(psql, "get_pool", return_value=pool):
            await psql.count_reports(None, 7)
            await psql.get_reports(20, 0, None, 7)

        count_call = pool.fetchval.await_args_list[0]
        page_call = pool.fetch.await_args_list[0]
        self.assertEqual(count_call.args[1:], (None, 7))
        self.assertEqual(page_call.args[1:], (None, 7, 20, 0))
        self.assertIn("Asia/Bangkok", count_call.args[0])

    async def test_statistics_queries_only_count_downloaded_images(self):
        pool = AsyncMock()
        pool.fetchrow.return_value = Record(total=0)
        pool.fetch.return_value = []
        with patch.object(psql, "get_pool", return_value=pool):
            await psql.get_report_media_coverage(30)
            await psql.get_report_daily_counts(30)

        summary_sql = pool.fetchrow.await_args_list[0].args[0]
        self.assertIn("JOIN images image", summary_sql)
        self.assertIn("btrim(image.image_key) <> ''", summary_sql)
        self.assertIn("FROM locations loc", summary_sql)
        self.assertIn("loc.lat IS NOT NULL", summary_sql)
        self.assertIn("loc.lon IS NOT NULL", summary_sql)
        self.assertIn("Asia/Bangkok", summary_sql)
        self.assertIn("generate_series", pool.fetch.await_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
