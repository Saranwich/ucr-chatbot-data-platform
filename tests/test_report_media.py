"""รูปจาก transcript ถูกตรวจและผูก report ผ่าน report_images โดยไม่ให้โมเดลอ้างรูปมั่ว"""

import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.clients import psql
from app.schemas.report import Report
from app.schemas.user import User
from app.services import ai_tools, chatbot
from tests.support import patch_log


SESSION_ID = uuid4()


def save_call(report: dict) -> dict:
    return {
        "type": "function",
        "function": {"name": "save_analyse", "arguments": json.dumps({"reports": [report]})},
    }


class ImageMarkerTest(unittest.IsolatedAsyncioTestCase):
    async def test_transcript_marker_contains_stable_image_id_but_no_image_claim(self):
        saved = AsyncMock()
        user = User(id=uuid4(), line_user_id="U-image")
        with (
            patch.object(chatbot.line_cli, "get_image_content", new=AsyncMock(return_value=("line://1", b"data", "image/jpeg"))),
            patch.object(chatbot.storage, "save_image", return_value="images/one.jpg"),
            patch.object(chatbot.psql, "save_image", new=saved),
        ):
            turn = await chatbot.message_image_handler(user, SESSION_ID, 2, {"id": "line-message"})

        image = saved.await_args.args[0]
        self.assertEqual(turn.content, f"[got image from user: image_id={image.id}]")
        self.assertEqual(image.image_key, "images/one.jpg")
        self.assertIn("มองเนื้อหารูปไม่เห็น", ai_tools.SET_FINISHED_PROTOCOL)

    async def test_failed_download_has_no_usable_image_id_marker(self):
        saved = AsyncMock()
        user = User(id=uuid4(), line_user_id="U-broken-image")
        with (
            patch.object(chatbot.line_cli, "get_image_content", new=AsyncMock(return_value=("line://broken", None, None))),
            patch.object(chatbot.psql, "save_image", new=saved),
            patch.object(chatbot.psql, "create_and_save_log", new=AsyncMock()),
        ):
            turn = await chatbot.message_image_handler(user, SESSION_ID, 3, {"id": "broken"})

        image = saved.await_args.args[0]
        self.assertIsNone(image.image_key)
        self.assertEqual(turn.content, "[image download failed]")
        self.assertNotIn(str(image.id), turn.content)


class AnalyzerImageLinkTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = patch_log(ai_tools).start()
        self.save_media = patch.object(
            ai_tools.psql, "save_report_with_media", new=AsyncMock(return_value=uuid4())
        ).start()
        self.save_report = patch.object(ai_tools.psql, "save_report", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    async def test_image_ids_are_parsed_and_force_image_flag_true(self):
        image_id = uuid4()
        result = await ai_tools.run_tool_calls(
            SESSION_ID, [save_call({"title": "ขยะ", "is_has_image": False, "image_ids": [str(image_id)], "location_ids": []})]
        )

        self.assertTrue(result.is_success)
        report, locations, images = self.save_media.await_args.args
        self.assertTrue(report.is_has_image)
        self.assertEqual((locations, images), ([], [image_id]))
        self.save_report.assert_not_awaited()

    async def test_claiming_image_without_id_is_rejected(self):
        result = await ai_tools.run_tool_calls(
            SESSION_ID, [save_call({"title": "ขยะ", "is_has_image": True, "image_ids": [], "location_ids": []})]
        )
        self.assertFalse(result.is_success)
        self.save_media.assert_not_awaited()
        self.save_report.assert_not_awaited()

    def test_schema_exposes_image_ids_and_not_image_contents(self):
        item = ai_tools.SAVE_ANALYSE_TOOL["function"]["parameters"]["properties"]["reports"]["items"]
        self.assertIn("image_ids", item["required"])
        self.assertEqual(item["properties"]["image_ids"]["items"]["format"], "uuid")
        self.assertIn("มองเห็นรูป", item["properties"]["image_ids"]["description"])


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class MediaConnection:
    def __init__(self, image_ids):
        self.image_ids = image_ids
        self.executions = []

    def transaction(self):
        return AsyncContext(self)

    async def fetch(self, query, *args):
        if "FROM images" in query:
            return [{"id": image_id} for image_id in self.image_ids]
        raise AssertionError(query)

    async def execute(self, query, *args):
        self.executions.append((query, args))
        return "INSERT 0 1"


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class MediaTransactionTest(unittest.IsolatedAsyncioTestCase):
    async def test_report_and_all_image_links_share_one_transaction(self):
        image_ids = [uuid4(), uuid4()]
        connection = MediaConnection(image_ids)
        report = Report(session_id=SESSION_ID, title="สองรูป", is_has_image=True)
        with patch.object(psql, "get_pool", return_value=FakePool(connection)):
            result = await psql.save_report_with_media(report, [], image_ids)

        self.assertEqual(result, report.id)
        self.assertEqual(len(connection.executions), 2)
        self.assertIn("INSERT INTO reports", connection.executions[0][0])
        self.assertIn("INSERT INTO report_images", connection.executions[1][0])

    async def test_missing_or_undownloaded_image_stops_before_report_write(self):
        connection = MediaConnection([])
        report = Report(session_id=SESSION_ID, title="รูปเสีย", is_has_image=True)
        with patch.object(psql, "get_pool", return_value=FakePool(connection)):
            result = await psql.save_report_with_media(report, [], [uuid4()])
        self.assertIsNone(result)
        self.assertEqual(connection.executions, [])

    async def test_two_reports_sharing_one_image_keep_distinct_ids_and_links(self):
        image_id = uuid4()
        connection = MediaConnection([image_id])
        first = Report(session_id=SESSION_ID, title="ถนนพัง", is_has_image=True)
        second = Report(session_id=SESSION_ID, title="ขยะ", is_has_image=True)
        with patch.object(psql, "get_pool", return_value=FakePool(connection)):
            first_id = await psql.save_report_with_media(first, [], [image_id])
            second_id = await psql.save_report_with_media(second, [], [image_id])

        self.assertEqual((first_id, second_id), (first.id, second.id))
        link_writes = [args for query, args in connection.executions if "INSERT INTO report_images" in query]
        self.assertEqual(link_writes, [(first.id, [image_id]), (second.id, [image_id])])


if __name__ == "__main__":
    unittest.main()
