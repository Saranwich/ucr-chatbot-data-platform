"""services/communicator_output — บันไดกู้คำตอบ ตั้งแต่ JSON ครบรูปจนถึงโมเดลลืมรูปไปเลย

เทสต์ชุดนี้คุมกติกาเดียว: ยอมเสียธงกับปุ่ม แต่ห้ามเสียข้อความ
เสียธง = ปิดบทสนทนาช้าไปสิบนาที / เสียข้อความ = ชาวบ้านโดนเงียบใส่ ซึ่งคือบั๊กที่เราเพิ่งแก้มา
"""

import json
import unittest
from unittest.mock import patch

from app.services import communicator_output as output
from tests.support import patch_log

parse = output.parse_communicator_reply


class ParseCommunicatorReplyTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.log = patch_log(output).start()
        self.addCleanup(patch.stopall)

    async def test_json_ครบรูป_ได้ครบทั้งสามอย่าง (self):
        reply = await parse(json.dumps({
            "reply_text": "ท่วมสูงแค่ไหนคะ",
            "is_finished": False,
            "quick_replies": [
                {"type": "message", "label": "ถึงเข่า", "text": "ถึงเข่า"},
                {"type": "message", "label": "ถึงเอว", "text": "ถึงเอว"},
            ],
        }, ensure_ascii=False))

        self.assertEqual(reply.reply_text, "ท่วมสูงแค่ไหนคะ")
        self.assertFalse(reply.is_finished)
        self.assertEqual([item.label for item in reply.quick_replies], ["ถึงเข่า", "ถึงเอว"])
        self.log.assert_not_awaited()

    async def test_ขาดช่องที่ไม่ใช่ข้อความ_ยังใช้ได้ (self):
        """สองช่องนั้นมีค่าตั้งต้น ขาดมาก็แค่กลับไปเป็นพฤติกรรมเดิมของระบบ"""
        reply = await parse('{"reply_text": "สวัสดีค่ะ"}')

        self.assertEqual(reply.reply_text, "สวัสดีค่ะ")
        self.assertFalse(reply.is_finished)
        self.assertEqual(reply.quick_replies, [])

    async def test_ครอบรั้วโค้ดมา_ลอกออกแล้วใช้ต่อ (self):
        reply = await parse('```json\n{"reply_text": "สวัสดีค่ะ", "is_finished": true}\n```')

        self.assertEqual(reply.reply_text, "สวัสดีค่ะ")
        self.assertTrue(reply.is_finished)

    async def test_มีคำพูดนำหน้า_json_ยังคว้าก้อนในปีกกาได้ (self):
        reply = await parse('นี่คือคำตอบครับ\n{"reply_text": "สวัสดีค่ะ", "is_finished": false}')

        self.assertEqual(reply.reply_text, "สวัสดีค่ะ")

    async def test_ร้อยแก้วล้วน_เอาทั้งก้อนไปตอบ (self):
        """วัดจากของจริง 2/72 ครั้ง และทั้งสองครั้งเป็นคำตอบที่ดีสมบูรณ์"""
        reply = await parse("  ขอบคุณค่ะ น้ำท่วมที่นั่นบ่อยไหมคะ  ")

        self.assertEqual(reply.reply_text, "ขอบคุณค่ะ น้ำท่วมที่นั่นบ่อยไหมคะ")
        self.assertFalse(reply.is_finished)
        self.assertEqual(reply.quick_replies, [])
        self.log.assert_awaited()

    async def test_json_พังแต่ยังเห็น_reply_text_กู้เฉพาะข้อความ (self):
        """ขึ้นบรรทัดจริงในเนื้อสตริงคือสาเหตุที่ json พังบ่อยที่สุด"""
        raw = '{"reply_text": "สวัสดีค่ะ\nวันนี้มีอะไรอยากเล่าไหมคะ", "is_finished": true'

        reply = await parse(raw)

        self.assertEqual(reply.reply_text, "สวัสดีค่ะ\nวันนี้มีอะไรอยากเล่าไหมคะ")
        # ธงในก้อนที่พังเชื่อไม่ได้ ทิ้งทั้งตา
        self.assertFalse(reply.is_finished)
        self.log.assert_awaited()

    async def test_json_พังและหา_reply_text_ไม่เจอ_ยอมเงียบ (self):
        """ส่งปีกกาไปให้ชาวบ้านอ่านแย่กว่าเงียบ"""
        self.assertIsNone(await parse('{"is_finished": true, "quick_replies": ['))
        self.log.assert_awaited()

    async def test_json_ใช้ได้แต่ไม่มี_reply_text_คืน_None (self):
        self.assertIsNone(await parse('{"is_finished": true, "quick_replies": []}'))
        self.assertIsNone(await parse('{"reply_text": "   "}'))

    async def test_ไม่มีอะไรมาเลย_คืน_None (self):
        for raw in (None, "", "   ", 7):
            with self.subTest(raw=raw):
                self.assertIsNone(await parse(raw))

    async def test_ธงเป็นสตริง_true_ยังนับให้ (self):
        """โมเดลพิมพ์ boolean เป็นสตริงบ่อยพอที่จะเสียธงฟรี ๆ"""
        reply = await parse('{"reply_text": "ขอบคุณค่ะ", "is_finished": "true"}')

        self.assertTrue(reply.is_finished)

    async def test_ธงเป็นค่าที่แปลไม่ออก_ถือว่ายังไม่จบ (self):
        """ปักผิดว่าจบ = ตัดบทสนทนาของชาวบ้านทิ้งกลางคัน เดาให้ไม่ได้"""
        for value in ("1", 1, "ใช่", None, [], "yes"):
            with self.subTest(value=value):
                reply = await parse(json.dumps({"reply_text": "ค่ะ", "is_finished": value}))
                self.assertFalse(reply.is_finished)


class PastReplyTest (unittest.IsolatedAsyncioTestCase):
    """ตาเก่าของบอทที่ใส่กลับเข้าประวัติ ต้องเป็นรูปเดียวกับที่เราขอให้มันคาย"""

    def setUp (self):
        patch_log(output).start()
        self.addCleanup(patch.stopall)

    async def test_เขียนกลับแล้วแกะได้ข้อความเดิม (self):
        reply = await parse(output.past_reply_as_json("ท่วมสูงแค่ไหนคะ"))

        self.assertEqual(reply.reply_text, "ท่วมสูงแค่ไหนคะ")
        self.assertFalse(reply.is_finished)
        self.assertEqual(reply.quick_replies, [])

    async def test_ไม่หนีเป็น_unicode_escape (self):
        """ประวัติต้องอ่านออกด้วยตาตอนไล่ log ไม่ใช่กองเลข \\uXXXX"""
        self.assertIn("ท่วมสูงแค่ไหนคะ", output.past_reply_as_json("ท่วมสูงแค่ไหนคะ"))

    async def test_ข้อความมีอัญประกาศกับขึ้นบรรทัด_ยังกลับมาครบ (self):
        text = 'เขาบอกว่า "น้ำท่วม"\nแล้วก็ขังนาน'

        reply = await parse(output.past_reply_as_json(text))

        self.assertEqual(reply.reply_text, text)


class ContractTest (unittest.TestCase):
    """สัญญากับ schema ต้องพูดตรงกัน ไม่งั้นโมเดลได้ยินคนละเรื่องกับที่เรารอ"""

    def test_schema_มีช่องตรงกับ_CommunicatorReply (self):
        from app.schemas.communicator import CommunicatorReply

        schema = output.RESPONSE_FORMAT["json_schema"]["schema"]
        self.assertEqual(set(schema["properties"]), set(CommunicatorReply.model_fields))
        self.assertEqual(sorted(schema["required"]), sorted(CommunicatorReply.model_fields))
        self.assertFalse(schema["additionalProperties"])

    def test_สัญญาย้ำเคสตอบสั้นว่ายังไม่จบ (self):
        """วัดแล้วโมเดลปัก true ให้คำว่า ok ทุกครั้ง 9/9 ต้องเขียนดักไว้ตรง ๆ"""
        contract = output.COMMUNICATOR_OUTPUT_CONTRACT
        self.assertIn('"ok"', contract)
        self.assertIn("ไม่ใช่การบอกลา", contract)
        self.assertIn("ไม่แน่ใจให้ใส่ false", contract)

    def test_สัญญายังสอนเรื่องป้ายจากระบบ (self):
        """ป้ายรูปกับพิกัดไม่เกี่ยวกับ tool calling ย้ายบ้านแล้วต้องไม่หายไปด้วย"""
        contract = output.COMMUNICATOR_OUTPUT_CONTRACT
        self.assertIn("got image from user", contract)
        self.assertIn("image download failed", contract)
        self.assertIn("got location from user", contract)


if __name__ == "__main__":
    unittest.main()
