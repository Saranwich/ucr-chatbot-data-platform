"""clients/line — จุดสามจุดเป็นของประดับ ล้มยังไงก็ห้ามโยนขึ้นไปหาคนเรียก"""

import unittest
from unittest.mock import patch

import httpx

from app.clients import line
from tests.support import FakeAsyncClient, FakeResponse, patch_log


class StartLoadingTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.recorder = {}
        self.log = patch_log(line).start()
        self.addCleanup(patch.stopall)

    def serve (self, response):
        patch.object(
            line.httpx, "AsyncClient", lambda timeout=None: FakeAsyncClient(response, self.recorder)
        ).start()

    async def test_ยิงตาม_spec_ของไลน์ (self):
        self.serve(FakeResponse(202))

        await line.start_loading("U-test")

        self.assertEqual(self.recorder["url"], line.LINE_LOADING_URL)
        self.assertEqual(self.recorder["body"]["chatId"], "U-test")
        self.assertEqual(self.recorder["body"]["loadingSeconds"], line.LOADING_SECONDS)
        self.log.assert_not_awaited()

    async def test_วินาทีอยู่ในช่วงที่ไลน์รับ (self):
        """ไลน์รับ 5-60 และต้องเป็นจำนวนเท่าของ 5"""
        self.assertGreaterEqual(line.LOADING_SECONDS, 5)
        self.assertLessEqual(line.LOADING_SECONDS, 60)
        self.assertEqual(line.LOADING_SECONDS % 5, 0)

    async def test_ไลน์ไม่รับ_log_แล้วเงียบ (self):
        self.serve(FakeResponse(400, text="bad request"))

        await line.start_loading("U-test")

        self.log.assert_awaited_once()

    async def test_ยิงไม่ถึง_ไม่โยนต่อ (self):
        self.serve(httpx.ConnectTimeout("ต่อไม่ติด"))

        await line.start_loading("U-test")

        self.log.assert_awaited_once()

    async def test_เด้งอย่างอื่น_ก็ไม่โยนต่อ (self):
        """คนเรียกอยู่กลางทางไปหาคำตอบ สะดุดตรงนี้แล้วชาวบ้านไม่ได้คำตอบเลยไม่คุ้ม"""
        self.serve(RuntimeError("อะไรก็ไม่รู้"))

        await line.start_loading("U-test")

        self.log.assert_awaited_once()
