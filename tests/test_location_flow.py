"""วงจร location จาก LINE จน locations.report_id ชี้กลับไปยัง report ที่ analyzer สร้าง"""

import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.clients import psql
from app.schemas.report import Location, Report
from app.schemas.user import User
from app.services import ai_tools, chatbot
from tests.support import patch_log


SESSION_ID = uuid4()


def save_analyse_call(reports: list[dict]) -> dict:
    return {
        "id": "save_1",
        "type": "function",
        "function": {
            "name": "save_analyse",
            "arguments": json.dumps({"reports": reports}),
        },
    }


class LocationMessageHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_เก็บพิกัดจริงแต่ส่งให้โมเดลเห็นแค่_location_id(self):
        save_location = AsyncMock()
        user = User(id=uuid4(), line_user_id="U-location")

        with patch.object(chatbot.psql, "save_location", new=save_location):
            turn = await chatbot.message_location_handler(
                user,
                SESSION_ID,
                3,
                {"latitude": 13.7563, "longitude": 100.5018, "address": "จุดทดสอบ"},
            )

        location = save_location.await_args.args[0]
        self.assertEqual(location.session_id, SESSION_ID)
        self.assertEqual(location.number, 3)
        self.assertEqual((location.lat, location.lon, location.address), (13.7563, 100.5018, "จุดทดสอบ"))
        self.assertIsNone(location.report_id)
        self.assertEqual(turn.content, f"[got location from user: location_id={location.id}]")
        self.assertNotIn("13.7563", turn.content)
        self.assertNotIn("100.5018", turn.content)

    async def test_location_ไม่มีพิกัดครบคู่ถูกทิ้งและ_log(self):
        save_location = AsyncMock()
        log = AsyncMock()
        user = User(id=uuid4(), line_user_id="U-bad-location")

        with (
            patch.object(chatbot.psql, "save_location", new=save_location),
            patch.object(chatbot.psql, "create_and_save_log", new=log),
        ):
            turn = await chatbot.message_location_handler(
                user,
                SESSION_ID,
                1,
                {"latitude": 13.7563},
            )

        self.assertIsNone(turn)
        save_location.assert_not_awaited()
        self.assertTrue(any("location ที่อ่านไม่ได้" in call.args[1] for call in log.await_args_list))


class LocationReportLinkTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = patch_log(ai_tools).start()
        self.linked_report_id = uuid4()
        self.save_report = patch.object(
            ai_tools.psql, "save_report", new=AsyncMock(return_value=self.linked_report_id)
        ).start()
        self.addCleanup(patch.stopall)

    async def run_reports(self, reports: list[dict]):
        return await ai_tools.run_tool_calls(SESSION_ID, [save_analyse_call(reports)])

    async def test_location_id_ที่ถูกต้องถูกผูกกับ_report_ที่ระบบสร้าง(self):
        location_id = uuid4()

        outcome = await self.run_reports([
            {
                "title": "น้ำท่วมหน้าบ้าน",
                "is_has_location": False,
                "location_ids": [str(location_id)],
            }
        ])

        self.assertTrue(outcome.is_success)
        self.assertEqual((outcome.requested, outcome.saved), (1, 1))
        report, location_ids, image_ids = self.save_report.await_args.args
        self.assertEqual(location_ids, [location_id])
        self.assertEqual(image_ids, [])
        self.assertEqual(report.session_id, SESSION_ID)
        self.assertTrue(report.is_has_location)

    async def test_location_ไม่อยู่ใน_session_หรือไม่มีจริง_ต้อง_retry(self):
        self.save_report.return_value = None

        outcome = await self.run_reports([
            {"title": "ไฟดับ", "location_ids": [str(uuid4())]}
        ])

        self.assertFalse(outcome.is_success)
        self.assertEqual((outcome.requested, outcome.saved), (1, 0))
        self.assertTrue(any("คนละ session" in call.args[1] for call in self.log.await_args_list))

    async def test_location_id_ผิดรูปไม่แตะฐาน(self):
        outcome = await self.run_reports([
            {"title": "น้ำท่วม", "location_ids": ["ไม่ใช่ uuid"]}
        ])

        self.assertFalse(outcome.is_success)
        self.save_report.assert_not_awaited()

    async def test_อ้างว่ามีพิกัดแต่ไม่ส่ง_id_ไม่สร้าง_false_positive(self):
        outcome = await self.run_reports([
            {"title": "น้ำท่วม", "is_has_location": True, "location_ids": []}
        ])

        self.assertFalse(outcome.is_success)
        self.save_report.assert_not_awaited()

    async def test_ไม่มีพิกัดยังบันทึก_report_ได้ตามเดิม(self):
        outcome = await self.run_reports([
            {"title": "อากาศร้อน", "is_has_location": False, "location_ids": []}
        ])

        self.assertTrue(outcome.is_success)
        report, location_ids, _ = self.save_report.await_args.args
        self.assertFalse(report.is_has_location)
        self.assertEqual(location_ids, [])

    async def test_location_เดียวกันผูกได้แค่_report_แรกใน_tool_call(self):
        location_id = str(uuid4())

        outcome = await self.run_reports([
            {"title": "เรื่องแรก", "location_ids": [location_id]},
            {"title": "เรื่องสอง", "location_ids": [location_id]},
        ])

        self.assertFalse(outcome.is_success)
        self.assertEqual((outcome.requested, outcome.saved), (2, 1))
        self.save_report.assert_awaited_once()
        self.assertTrue(any("หลาย report" in call.args[1] for call in self.log.await_args_list))

    def test_tool_schema_บอกให้ส่ง_location_ids_แต่ไม่เปิดช่องให้ส่งพิกัดจริง(self):
        item = ai_tools.SAVE_ANALYSE_TOOL["function"]["parameters"]["properties"]["reports"]["items"]

        self.assertIn("location_ids", item["required"])
        self.assertEqual(item["properties"]["location_ids"]["items"]["format"], "uuid")
        for forbidden in ("session_id", "report_id", "lat", "lon"):
            self.assertNotIn(forbidden, item["properties"])


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, available_ids, report_id=None, report_session_id=None):
        self.available_ids = available_ids
        self.report_id = report_id
        self.report_session_id = report_session_id
        self.executions = []

    def transaction(self):
        return AsyncContext(self)

    async def fetch(self, query, location_ids, session_id):
        return [
            {
                "id": value,
                "report_id": self.report_id,
                "report_session_id": self.report_session_id,
            }
            for value in self.available_ids
        ]

    async def execute(self, query, *args):
        self.executions.append((query, args))
        if "UPDATE locations" in query:
            return f"UPDATE {len(args[1])}"
        return "INSERT 0 1"


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class LocationTransactionTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_กับ_location_ถูกเขียนใน_transaction_เดียว(self):
        location_ids = [uuid4(), uuid4()]
        connection = FakeConnection(location_ids)
        report = Report(session_id=SESSION_ID, title="สองพิกัด", is_has_location=True)

        with patch.object(psql, "get_pool", return_value=FakePool(connection)):
            linked = await psql.save_report(report, location_ids)

        self.assertEqual(linked, report.id)
        self.assertEqual(len(connection.executions), 2)
        self.assertIn("INSERT INTO reports", connection.executions[0][0])
        self.assertIn("UPDATE locations", connection.executions[1][0])
        self.assertEqual(connection.executions[1][1], (report.id, location_ids, SESSION_ID))

    async def test_location_ตรวจไม่ครบแล้วไม่เขียน_report(self):
        location_ids = [uuid4(), uuid4()]
        connection = FakeConnection(location_ids[:1])
        report = Report(session_id=SESSION_ID, title="อ้างพิกัดที่ไม่มี", is_has_location=True)

        with patch.object(psql, "get_pool", return_value=FakePool(connection)):
            linked = await psql.save_report(report, location_ids)

        self.assertFalse(linked)
        self.assertEqual(connection.executions, [])

    async def test_retry_ใช้_report_id_เดิมและอัปเดตแทนสร้างซ้ำ(self):
        location_id = uuid4()
        existing_report_id = uuid4()
        connection = FakeConnection(
            [location_id],
            report_id=existing_report_id,
            report_session_id=SESSION_ID,
        )
        corrected = Report(session_id=SESSION_ID, title="รายละเอียดที่แก้แล้ว", is_has_location=True)

        with patch.object(psql, "get_pool", return_value=FakePool(connection)):
            linked = await psql.save_report(corrected, [location_id])

        self.assertEqual(linked, existing_report_id)
        insert_args = connection.executions[0][1]
        self.assertEqual(insert_args[0], existing_report_id)
        self.assertEqual(insert_args[4], "รายละเอียดที่แก้แล้ว")

    async def test_location_ที่ชี้_report_คนละ_session_ถูกปฏิเสธ(self):
        location_id = uuid4()
        connection = FakeConnection(
            [location_id],
            report_id=uuid4(),
            report_session_id=uuid4(),
        )
        report = Report(session_id=SESSION_ID, title="ห้ามย้ายเรื่องข้าม session", is_has_location=True)

        with patch.object(psql, "get_pool", return_value=FakePool(connection)):
            linked = await psql.save_report(report, [location_id])

        self.assertIsNone(linked)
        self.assertEqual(connection.executions, [])


class LocationSchemaTest(unittest.TestCase):
    def test_location_เก็บ_report_id_แบบ_nullable(self):
        location = Location(session_id=SESSION_ID, number=1, type="lat_lon", lat=1, lon=2)
        self.assertIsNone(location.report_id)

        report_id = uuid4()
        self.assertEqual(location.model_copy(update={"report_id": report_id}).report_id, report_id)


if __name__ == "__main__":
    unittest.main()
