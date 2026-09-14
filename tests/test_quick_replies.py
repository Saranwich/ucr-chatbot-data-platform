"""Quick reply จาก communicator tool call จนเป็น payload ที่ LINE รับ"""

import json
import unittest
from unittest.mock import patch

from app.clients import line
from app.core import default_value
from app.services import ai_tools
from tests.support import FakeAsyncClient, FakeResponse, patch_log


def quick_reply_call(items) -> dict:
    return {
        "id": "quick_1",
        "type": "function",
        "function": {
            "name": "set_finished_flag",
            "arguments": json.dumps(
                {"is_finished": False, "quick_replies": items}, ensure_ascii=False
            ),
        },
    }


def message_reply(label: str, text: str | None = None) -> dict:
    return {"type": "message", "label": label, "text": text if text is not None else label}


def location_reply(label: str = "แชร์พิกัด") -> dict:
    return {"type": "location", "label": label, "text": None}


class QuickReplyToolTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = patch_log(ai_tools).start()
        self.addCleanup(patch.stopall)

    async def test_schema_เพิ่ม_quick_reply_ใน_tool_เดิมของ_communicator(self):
        function = ai_tools.SET_FINISHED_FLAG_TOOL["function"]
        spec = function["parameters"]["properties"]["quick_replies"]

        self.assertEqual(function["name"], "set_finished_flag")
        self.assertIn("quick_replies", function["parameters"]["required"])
        self.assertEqual((spec["minItems"], spec["maxItems"]), (0, 5))
        self.assertEqual(spec["items"]["properties"]["type"]["enum"], ["message", "location"])
        self.assertEqual(spec["items"]["properties"]["label"]["maxLength"], 20)

    async def test_default_prompt_สอนเลือกปุ่มข้อความและปุ่มพิกัด(self):
        self.assertIn("type=message", default_value.COMMUNICATOR_PROMPT)
        self.assertIn("type=location", default_value.COMMUNICATOR_PROMPT)
        self.assertIn("แชร์พิกัด", default_value.COMMUNICATOR_PROMPT)

    async def test_อ่านตัวเลือกและตัดช่องว่างกับค่าซ้ำ(self):
        replies = await ai_tools.extract_quick_replies([
            quick_reply_call([
                message_reply(" ทุกครั้ง ", " ทุกครั้ง "),
                message_reply("บางครั้ง"),
                message_reply("ทุกครั้ง"),
            ])
        ])

        self.assertEqual(replies, [message_reply("ทุกครั้ง"), message_reply("บางครั้ง")])

    async def test_ตัดค่าผิดและจำกัดห้าปุ่ม(self):
        replies = await ai_tools.extract_quick_replies([
            quick_reply_call([
                *[message_reply(value) for value in ["หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก"]],
                message_reply("ยาวเกินยี่สิบตัวอักษรแน่นอนค่ะ"),
                message_reply("มี\nสองบรรทัด"),
                7,
            ])
        ])

        self.assertEqual(replies, [message_reply(value) for value in ["หนึ่ง", "สอง", "สาม", "สี่", "ห้า"]])

    async def test_เหลือไม่ถึงสองปุ่มแล้วไม่ส่ง_quick_reply(self):
        replies = await ai_tools.extract_quick_replies([
            quick_reply_call([
                message_reply("ตัวเดียว"),
                message_reply("ยาวเกินยี่สิบตัวอักษรแน่นอนค่ะ"),
            ])
        ])

        self.assertEqual(replies, [])
        self.log.assert_awaited()

    async def test_location_ปุ่มเดียวใช้ได้และไม่มี_text(self):
        replies = await ai_tools.extract_quick_replies([
            quick_reply_call([location_reply()])
        ])

        self.assertEqual(replies, [location_reply()])

    async def test_location_ที่มี_text_หรือ_type_แปลกถูกตัด(self):
        replies = await ai_tools.extract_quick_replies([
            quick_reply_call([
                {"type": "location", "label": "แชร์พิกัด", "text": "ผิดรูป"},
                {"type": "camera", "label": "ถ่ายรูป", "text": None},
            ])
        ])

        self.assertEqual(replies, [])

    async def test_label_ยาวยี่สิบผ่าน_แต่ยี่สิบเอ็ดถูกตัด(self):
        replies = await ai_tools.extract_quick_replies([
            quick_reply_call([
                message_reply("ก" * 20),
                message_reply("ข" * 21),
                message_reply("สั้น"),
            ])
        ])

        self.assertEqual(replies, [message_reply("ก" * 20), message_reply("สั้น")])

    async def test_label_นับ_emoji_ตาม_utf16_ของ_LINE(self):
        replies = await ai_tools.extract_quick_replies([
            quick_reply_call([
                message_reply("😀" * 10),
                message_reply("😀" * 11),
                message_reply("อีกตัวเลือก"),
            ])
        ])

        self.assertEqual(replies, [message_reply("😀" * 10), message_reply("อีกตัวเลือก")])

class LineQuickReplyPayloadTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log_patcher = patch_log(line)
        self.log_patcher.start()
        self.addCleanup(self.log_patcher.stop)

    async def test_quick_reply_ถูกแปะกับข้อความสุดท้าย(self):
        recorder = {}
        client = lambda timeout=None: FakeAsyncClient(FakeResponse(200, {}), recorder)

        with patch.object(line.httpx, "AsyncClient", client):
            status = await line.replie(
                "reply-token",
                ["คำถามค่ะ"],
                quick_replies=[
                    message_reply("ทุกครั้ง"),
                    message_reply("บางครั้ง"),
                    location_reply(),
                ],
            )

        self.assertEqual(status, 200)
        message = recorder["body"]["messages"][0]
        self.assertEqual(
            message["quickReply"]["items"],
            [
                {"type": "action", "action": {"type": "message", "label": "ทุกครั้ง", "text": "ทุกครั้ง"}},
                {"type": "action", "action": {"type": "message", "label": "บางครั้ง", "text": "บางครั้ง"}},
                {"type": "action", "action": {"type": "location", "label": "แชร์พิกัด"}},
            ],
        )

    async def test_ไม่มีตัวเลือกแล้ว_payload_เหมือนเดิม(self):
        recorder = {}
        client = lambda timeout=None: FakeAsyncClient(FakeResponse(200, {}), recorder)

        with patch.object(line.httpx, "AsyncClient", client):
            await line.replie("reply-token", ["ข้อความธรรมดา"], quick_replies=[])

        self.assertNotIn("quickReply", recorder["body"]["messages"][0])


if __name__ == "__main__":
    unittest.main()
