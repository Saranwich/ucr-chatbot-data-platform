"""clients/google_ai — หน้าตาต้องเหมือน typhoon ทุกจุด และต้องไม่ทำลายลายเซ็นความคิดของกูเกิล"""

import inspect
import unittest
from unittest.mock import patch

import httpx

from app.clients import google_ai, typhoon
from tests.support import FakeAsyncClient, FakeResponse, patch_log

# tool call ของ gemini 3 — extra_content คือของที่ต้องส่งกลับไปตาหน้า ขาดแล้วมันตอบ 400
TOOL_CALLS = [
    {
        "id": "call_1",
        "type": "function",
        "function": {"name": "save_analyse", "arguments": '{"reports": []}'},
        "extra_content": {"google": {"thought_signature": "ลายเซ็นยาว ๆ ที่เราอ่านไม่ออก"}},
    }
]


class GoogleAiClientTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.recorder = {}
        self.log = patch_log(google_ai).start()
        patch.object(google_ai, "GOOGLE_AI_API_KEY", "คีย์ปลอม").start()
        self.addCleanup(patch.stopall)

    def serve (self, response):
        patch.object(
            google_ai.httpx, "AsyncClient", lambda timeout=None: FakeAsyncClient(response, self.recorder)
        ).start()

    async def test_เสียบแทน_typhoon_ได้_พารามิเตอร์ตรงกันทุกตัว (self):
        """เขียนไว้เพื่อให้สลับ provider ได้ด้วยการเปลี่ยนชื่อโมดูลอย่างเดียว ไม่ต้องแก้คนเรียก"""
        for name in ("chat", "chat_with_tools"):
            with self.subTest(name):
                self.assertEqual(
                    inspect.signature(getattr(google_ai, name)),
                    inspect.signature(getattr(typhoon, name)),
                )

    async def test_ยิงไปที่หน้า_openai_compatible_พร้อมคีย์ (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "สวัสดีค่ะ"}}]}))

        reply = await google_ai.chat([{"role": "user", "content": "หวัดดี"}], "โมเดล", 0.7, 512)

        self.assertEqual(reply, "สวัสดีค่ะ")
        self.assertEqual(
            self.recorder["url"],
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        )
        self.assertEqual(self.recorder["headers"]["Authorization"], "Bearer คีย์ปลอม")
        self.assertEqual(self.recorder["body"]["model"], "โมเดล")
        self.assertEqual(self.recorder["body"]["temperature"], 0.7)
        self.assertEqual(self.recorder["body"]["max_tokens"], 512)

    async def test_chat_ส่ง_response_format_ให้ถ้าคนเรียกขอ (self):
        """ฝั่งกูเกิลบังคับตามช่องนี้จริง ตกหล่นเมื่อไหร่ได้ร้อยแก้วกลับมาแทน JSON"""
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "{}"}}]}))
        fmt = {"type": "json_schema", "json_schema": {"name": "x", "strict": True, "schema": {}}}

        await google_ai.chat([], "โมเดล", 0.7, 512, response_format=fmt)

        self.assertEqual(self.recorder["body"]["response_format"], fmt)

    async def test_chat_ไม่ส่ง_tools_ไปด้วย (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "ค่ะ"}}]}))

        await google_ai.chat([], "โมเดล", 0.7, 512)

        self.assertNotIn("tools", self.recorder["body"])
        self.assertNotIn("tool_choice", self.recorder["body"])
        self.assertNotIn("response_format", self.recorder["body"])

    async def test_chat_ไม่_200_คืน_None_แล้ว_log (self):
        self.serve(FakeResponse(500, None, "พัง"))

        self.assertIsNone(await google_ai.chat([], "โมเดล", 0.7, 512))
        self.log.assert_awaited()

    async def test_ไม่ได้ตั้งคีย์_ไม่ยิงเลย_แค่_log (self):
        """ยังไม่บังคับตั้งใน .env เครื่องที่ยังไม่ตั้งต้องรู้ตัวจาก log ไม่ใช่จาก 401 ของกูเกิล"""
        patch.object(google_ai, "GOOGLE_AI_API_KEY", "").start()
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "ไม่ควรถึงตรงนี้"}}]}))

        self.assertIsNone(await google_ai.chat_with_tools([], [], "โมเดล", 0.3, 512))
        self.assertNotIn("url", self.recorder)
        self.log.assert_awaited()

    async def test_คืน_tool_calls_ทั้งก้อน_ลายเซ็นความคิดต้องไม่หาย (self):
        """gemini 3 บังคับให้ส่ง thought_signature กลับไปตาหน้า แกะทิ้งที่นี่ = 400 ตอนยิงรอบสอง"""
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": None, "tool_calls": TOOL_CALLS}}]}))

        message = await google_ai.chat_with_tools([], [{"type": "function"}], "โมเดล", 0.3, 512)

        self.assertEqual(message["tool_calls"], TOOL_CALLS)
        self.assertIn("content", message)

    async def test_ส่ง_tools_กับ_tool_choice_auto_เป็นค่าตั้งต้น (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "", "tool_calls": []}}]}))
        tools = [{"type": "function", "function": {"name": "save_analyse"}}]

        await google_ai.chat_with_tools([], tools, "โมเดล", 0.3, 512)

        self.assertEqual(self.recorder["body"]["tools"], tools)
        self.assertEqual(self.recorder["body"]["tool_choice"], "auto")

    async def test_รับ_tool_choice_จากคนเรียก (self):
        self.serve(FakeResponse(200, {"choices": [{"message": {"content": "ค่ะ"}}]}))

        await google_ai.chat_with_tools([], [], "โมเดล", 0.3, 512, tool_choice="none")

        self.assertEqual(self.recorder["body"]["tool_choice"], "none")

    async def test_response_ผิดรูป_คืน_None (self):
        self.serve(FakeResponse(200, {"ไม่มีช่อง choices": True}))

        self.assertIsNone(await google_ai.chat_with_tools([], [], "โมเดล", 0.3, 512))
        self.log.assert_awaited()

    async def test_เน็ตพัง_คืน_None_ไม่โยนออกไป (self):
        """ตัวกวาดเรียกตัวนี้ ปล่อยให้โยนทะลุแปลว่า session ค้าง pending ตลอดไป"""
        self.serve(httpx.ConnectError("ต่อไม่ติด"))

        self.assertIsNone(await google_ai.chat_with_tools([], [], "โมเดล", 0.3, 512))
        self.log.assert_awaited()


if __name__ == "__main__":
    unittest.main()
