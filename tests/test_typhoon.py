"""clients/typhoon — ทางเดิมของ communicator ต้องไม่ขยับ ทางใหม่ต้องเก็บ tool_calls ไว้ครบ"""

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.clients import typhoon
from tests.support import FakeAsyncClient, FakeResponse, patch_log

TOOL_CALLS = [
    {"id": "call_1", "type": "function", "function": {"name": "save_analyse", "arguments": '{"reports": []}'}}
]


class TyphoonClientTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.recorder = {}
        self.log = patch_log(typhoon).start()
        self.addCleanup(patch.stopall)

    def serve (self, response):
        patch.object(
            typhoon.httpx, "AsyncClient", lambda timeout=None: FakeAsyncClient(response, self.recorder)
        ).start()

    async def test_chat_ยังคืนข้อความเหมือนเดิม (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "สวัสดีค่ะ"}}]}))

        reply = await typhoon.chat([{"role": "user", "content": "หวัดดี"}], "โมเดล", 0.7, 512)

        self.assertEqual(reply, "สวัสดีค่ะ")
        self.assertEqual(self.recorder["body"]["model"], "โมเดล")
        self.assertEqual(self.recorder["body"]["temperature"], 0.7)
        self.assertEqual(self.recorder["body"]["max_tokens"], 512)

    async def test_chat_ไม่ส่ง_tools_ไปด้วย (self):
        """communicator ยังคุยแบบเดิม ไม่ควรมีช่อง tools/tool_choice โผล่ใน body"""
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "ค่ะ"}}]}))

        await typhoon.chat([], "โมเดล", 0.7, 512)

        self.assertNotIn("tools", self.recorder["body"])
        self.assertNotIn("tool_choice", self.recorder["body"])

    async def test_chat_ไม่_200_คืน_None_แล้ว_log (self):
        self.serve(FakeResponse(500, None, "พัง"))

        self.assertIsNone(await typhoon.chat([], "โมเดล", 0.7, 512))
        self.log.assert_awaited()

    async def test_chat_with_tools_เก็บ_tool_calls_ไว้ครบ (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": None, "tool_calls": TOOL_CALLS}}]}))

        message = await typhoon.chat_with_tools([], [{"type": "function"}], "โมเดล", 0.3, 512)

        self.assertEqual(message["tool_calls"], TOOL_CALLS)
        self.assertIn("content", message)

    async def test_chat_with_tools_ส่ง_tools_กับ_tool_choice_auto (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "", "tool_calls": []}}]}))
        tools = [{"type": "function", "function": {"name": "save_analyse"}}]

        await typhoon.chat_with_tools([], tools, "โมเดล", 0.3, 512)

        self.assertEqual(self.recorder["body"]["tools"], tools)
        self.assertEqual(self.recorder["body"]["tool_choice"], "auto")

    async def test_chat_with_tools_รับ_tool_choice_จากคนเรียก (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": None, "tool_calls": TOOL_CALLS}}]}))

        await typhoon.chat_with_tools([], [], "โมเดล", 0.3, 512, tool_choice="required")

        self.assertEqual(self.recorder["body"]["tool_choice"], "required")

    async def test_chat_with_tools_response_ผิดรูป_คืน_None (self):
        self.serve(FakeResponse(200, {"ไม่มีช่อง choices": True}))

        self.assertIsNone(await typhoon.chat_with_tools([], [], "โมเดล", 0.3, 512))
        self.log.assert_awaited()

    async def test_chat_with_tools_เน็ตพัง_คืน_None_ไม่โยนออกไป (self):
        """ตัวกวาดเรียกตัวนี้ ปล่อยให้โยนทะลุแปลว่า session ค้าง pending ตลอดไป"""
        self.serve(httpx.ConnectError("ต่อไม่ติด"))

        self.assertIsNone(await typhoon.chat_with_tools([], [], "โมเดล", 0.3, 512))
        self.log.assert_awaited()


if __name__ == "__main__":
    unittest.main()
