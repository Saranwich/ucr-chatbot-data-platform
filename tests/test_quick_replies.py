"""Quick reply จากช่องใน JSON ของ communicator จนเป็น payload ที่ LINE รับ

กติกาทุกข้อในชุดนี้เป็นของ LINE ไม่ใช่ของโมเดล ย้ายบ้านจาก tool call มาเป็นช่องใน JSON
แต่เนื้อกติกาไม่ขยับสักข้อ เทสต์ชุดนี้จึงยกมาทั้งชุดโดยเปลี่ยนแค่ทางเข้า
"""

import json
import unittest
from unittest.mock import patch

from app.clients import line
from app.core import default_value
from app.services import communicator_output
from tests.support import FakeAsyncClient, FakeResponse, patch_log


def model_says(items) -> str:
    """คำตอบดิบของโมเดลที่มีปุ่มชุดนี้ติดมา"""
    return json.dumps(
        {"reply_text": "ถามค่ะ", "is_finished": False, "quick_replies": items},
        ensure_ascii=False,
    )


def message_reply(label: str, text: str | None = None) -> dict:
    return {"type": "message", "label": label, "text": text if text is not None else label}


def location_reply(label: str = "แชร์พิกัด") -> dict:
    return {"type": "location", "label": label, "text": None}


async def read(items) -> list[dict]:
    """แกะคำตอบที่มีปุ่มชุดนี้ แล้วคืนปุ่มที่รอดออกมาเป็น dict ให้เทียบง่าย"""
    reply = await communicator_output.parse_communicator_reply(model_says(items))
    return [item.model_dump() for item in reply.quick_replies]


class QuickReplyFieldTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = patch_log(communicator_output).start()
        self.addCleanup(patch.stopall)

    async def test_สัญญาบอกรูปปุ่มครบทั้งสองชนิด(self):
        """สัญญาคือที่เดียวที่โมเดลได้เห็นรูปปุ่ม เขียนตกเมื่อไหร่มันเดาเอาเอง"""
        contract = communicator_output.COMMUNICATOR_OUTPUT_CONTRACT
        self.assertIn('"type":"message"', contract)
        self.assertIn('"type":"location"', contract)
        self.assertIn("20 ตัวอักษร", contract)

        spec = communicator_output.RESPONSE_FORMAT["json_schema"]["schema"]["properties"]["quick_replies"]
        self.assertEqual(spec["maxItems"], 5)
        self.assertEqual(spec["items"]["properties"]["type"]["enum"], ["message", "location"])
        self.assertEqual(spec["items"]["properties"]["label"]["maxLength"], 20)

    async def test_default_prompt_สอนเลือกปุ่มข้อความและปุ่มพิกัด(self):
        self.assertIn("type=message", default_value.COMMUNICATOR_PROMPT)
        self.assertIn("type=location", default_value.COMMUNICATOR_PROMPT)
        self.assertIn("แชร์พิกัด", default_value.COMMUNICATOR_PROMPT)

    async def test_อ่านตัวเลือกและตัดช่องว่างกับค่าซ้ำ(self):
        replies = await read([
            message_reply(" ทุกครั้ง ", " ทุกครั้ง "),
            message_reply("บางครั้ง"),
            message_reply("ทุกครั้ง"),
        ])

        self.assertEqual(replies, [message_reply("ทุกครั้ง"), message_reply("บางครั้ง")])

    async def test_ตัดค่าผิดและจำกัดห้าปุ่ม(self):
        replies = await read([
            *[message_reply(value) for value in ["หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก"]],
            message_reply("ยาวเกินยี่สิบตัวอักษรแน่นอนค่ะ"),
            message_reply("มี\nสองบรรทัด"),
            7,
        ])

        self.assertEqual(replies, [message_reply(value) for value in ["หนึ่ง", "สอง", "สาม", "สี่", "ห้า"]])

    async def test_เหลือไม่ถึงสองปุ่มแล้วไม่ส่ง_quick_reply(self):
        replies = await read([
            message_reply("ตัวเดียว"),
            message_reply("ยาวเกินยี่สิบตัวอักษรแน่นอนค่ะ"),
        ])

        self.assertEqual(replies, [])

    async def test_location_ปุ่มเดียวใช้ได้และไม่มี_text(self):
        self.assertEqual(await read([location_reply()]), [location_reply()])

    async def test_location_ที่มี_text_หรือ_type_แปลกถูกตัด(self):
        replies = await read([
            {"type": "location", "label": "แชร์พิกัด", "text": "ผิดรูป"},
            {"type": "camera", "label": "ถ่ายรูป", "text": None},
        ])

        self.assertEqual(replies, [])

    async def test_label_ยาวยี่สิบผ่าน_แต่ยี่สิบเอ็ดถูกตัด(self):
        replies = await read([
            message_reply("ก" * 20),
            message_reply("ข" * 21),
            message_reply("สั้น"),
        ])

        self.assertEqual(replies, [message_reply("ก" * 20), message_reply("สั้น")])

    async def test_label_นับ_emoji_ตาม_utf16_ของ_LINE(self):
        replies = await read([
            message_reply("😀" * 10),
            message_reply("😀" * 11),
            message_reply("อีกตัวเลือก"),
        ])

        self.assertEqual(replies, [message_reply("😀" * 10), message_reply("อีกตัวเลือก")])

    async def test_ปุ่มเสียทั้งช่อง_ข้อความยังรอด(self):
        """ปุ่มพังต้องไม่ลามไปทำให้คำตอบทั้งตาหาย นี่คือทั้งเหตุผลที่เราตรวจทีละปุ่ม"""
        reply = await communicator_output.parse_communicator_reply(
            json.dumps({"reply_text": "ถามค่ะ", "quick_replies": "ไม่ใช่ลิสต์"}, ensure_ascii=False)
        )

        self.assertEqual(reply.reply_text, "ถามค่ะ")
        self.assertEqual(reply.quick_replies, [])


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
