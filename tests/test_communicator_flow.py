"""เส้นทาง communicator เต็มเส้น — จากข้อความชาวบ้าน ถึงคำตอบใน LINE และธงจบในฐาน

จุดที่เทสต์ชุดนี้คุมคือ "ลำดับ" ไม่ใช่เนื้อคำตอบ
ปักธงก่อนตอบเมื่อไหร่ ตัวกวาดปิด session ทับระหว่างที่คำตอบยังไม่ถึงชาวบ้าน
"""

import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.schemas.user import User
from app.services import ai, chatbot


def model_says (reply_text: str, is_finished: bool = False, quick_replies=None) -> str:
    """คำตอบดิบก้อนเดียวแบบที่โมเดลคายมาจริง"""
    return json.dumps(
        {
            "reply_text": reply_text,
            "is_finished": is_finished,
            "quick_replies": quick_replies or [],
        },
        ensure_ascii=False,
    )


class CommunicatorFlowTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.user = User(id=uuid4(), line_user_id="U-test")
        self.session_id = uuid4()
        self.redis_key = f"session:{self.user.id}"

        patch.object(chatbot, "get_or_create_user", new=AsyncMock(return_value=self.user)).start()
        patch.object(
            chatbot,
            "load_session_from_redis",
            new=AsyncMock(return_value=(self.session_id, [])),
        ).start()
        patch.object(chatbot.psql, "save_message", new=AsyncMock()).start()
        self.set_finished = patch.object(
            chatbot.psql, "set_session_finished", new=AsyncMock(return_value=True)
        ).start()
        patch.object(chatbot, "save_session_to_redis", new=AsyncMock()).start()
        patch.object(chatbot.psql, "create_and_save_log", new=AsyncMock()).start()
        patch.object(chatbot.psql, "save_ai_response", new=AsyncMock()).start()
        self.reply = patch.object(chatbot.line_cli, "replie", new=AsyncMock()).start()
        self.loading = patch.object(chatbot.line_cli, "start_loading", new=AsyncMock()).start()
        self.provider = patch.object(ai.typhoon, "chat", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    async def say (self, text: str):
        await chatbot.handle_user_events(
            "U-test",
            [{
                "type": "message",
                "replyToken": "reply-token",
                "message": {"type": "text", "text": text},
            }],
        )

    async def test_บอกว่าจบแล้ว_ตอบผู้ใช้ก่อนแล้วค่อยปักธง (self):
        order = []

        async def remember_finished (session_id, value):
            order.append(f"finished:{value}")
            return True

        async def remember_reply (reply_token, messages, quick_replies=None):
            order.append("line_reply")

        self.set_finished.side_effect = remember_finished
        self.reply.side_effect = remember_reply
        self.provider.return_value = model_says("ขอบคุณที่มาเล่าให้ฟังนะคะ", is_finished=True)

        await self.say("จบแล้วครับ")

        self.assertEqual(
            [call.args for call in self.set_finished.await_args_list],
            [(self.session_id, False), (self.session_id, True)],
        )
        self.assertEqual(self.provider.await_count, 1)
        self.reply.assert_awaited_once_with(
            "reply-token", ["ขอบคุณที่มาเล่าให้ฟังนะคะ"], quick_replies=[]
        )
        self.assertEqual(order, ["finished:False", "line_reply", "finished:True"])

    async def test_ขึ้นจุดโหลดก่อนถามโมเดล (self):
        """จุดต้องขึ้นก่อนช่วงที่รอนาน ขึ้นหลังตอบไปแล้วก็ไม่มีประโยชน์"""
        order = []

        async def remember_loading (line_user_id):
            order.append(f"loading:{line_user_id}")

        async def remember_provider (*args, **kwargs):
            order.append("provider")
            return model_says("สวัสดีค่ะ")

        self.loading.side_effect = remember_loading
        self.provider.side_effect = remember_provider

        await self.say("สวัสดีครับ")

        self.assertEqual(order, ["loading:U-test", "provider"])

    async def test_ยังคุยอยู่_ไม่ปักธงจบเพิ่ม (self):
        self.provider.return_value = model_says("สวัสดีค่ะ มีเรื่องสภาพพื้นที่อยากเล่าไหมคะ")

        await self.say("อ้าว ทำไมเงียบ")

        # เหลือแค่ครั้งที่ chatbot ถอนให้ตอนรับข้อความ ไม่มีใครปักเพิ่ม
        self.assertEqual(
            [call.args for call in self.set_finished.await_args_list],
            [(self.session_id, False)],
        )
        self.provider.assert_awaited_once()
        self.reply.assert_awaited_once_with(
            "reply-token",
            ["สวัสดีค่ะ มีเรื่องสภาพพื้นที่อยากเล่าไหมคะ"],
            quick_replies=[],
        )

    async def test_ขอปุ่มแชร์พิกัด_แล้วส่ง_location_action_ไป_LINE (self):
        self.provider.return_value = model_says(
            "ช่วยแชร์พิกัดจุดที่น้ำท่วมได้ไหมคะ",
            quick_replies=[{"type": "location", "label": "แชร์พิกัด", "text": None}],
        )

        await self.say("ฝนตกแล้วน้ำท่วมค่ะ")

        self.reply.assert_awaited_once_with(
            "reply-token",
            ["ช่วยแชร์พิกัดจุดที่น้ำท่วมได้ไหมคะ"],
            quick_replies=[{"type": "location", "label": "แชร์พิกัด", "text": None}],
        )
        self.assertEqual(
            [call.args for call in self.set_finished.await_args_list],
            [(self.session_id, False)],
        )

    async def test_ได้ทั้งปุ่มและธงจบในตาเดียว (self):
        """สามอย่างอยู่ในก้อนเดียวกันแล้ว ไม่ต้องแยกคำสั่งให้มาพร้อมกันอีก"""
        self.provider.return_value = model_says(
            "ขอบคุณที่เล่าให้ฟังนะคะ",
            is_finished=True,
            quick_replies=[
                {"type": "message", "label": "มีอีกเรื่อง", "text": "มีอีกเรื่อง"},
                {"type": "message", "label": "พอแล้ว", "text": "พอแล้ว"},
            ],
        )

        await self.say("พอแค่นี้ครับ")

        self.provider.assert_awaited_once()
        self.reply.assert_awaited_once_with(
            "reply-token",
            ["ขอบคุณที่เล่าให้ฟังนะคะ"],
            quick_replies=[
                {"type": "message", "label": "มีอีกเรื่อง", "text": "มีอีกเรื่อง"},
                {"type": "message", "label": "พอแล้ว", "text": "พอแล้ว"},
            ],
        )
        self.assertEqual(
            [call.args for call in self.set_finished.await_args_list],
            [(self.session_id, False), (self.session_id, True)],
        )

    async def test_โมเดลลืมรูป_คายร้อยแก้ว_ชาวบ้านยังได้คำตอบ (self):
        """เคสนี้เกิดจริง 2/72 ครั้งตอนวัด ชาวบ้านต้องไม่โดนเงียบใส่เพราะวงเล็บหาย"""
        self.provider.return_value = "ขอบคุณค่ะ น้ำท่วมที่นั่นบ่อยไหมคะ"

        await self.say("[got location from user: location_id=8f2c1a]")

        self.reply.assert_awaited_once_with(
            "reply-token", ["ขอบคุณค่ะ น้ำท่วมที่นั่นบ่อยไหมคะ"], quick_replies=[]
        )

    async def test_ไม่มีคำตอบใช้ได้_ไม่ยิงอะไรออกไลน์ (self):
        self.provider.return_value = None

        await self.say("สวัสดีครับ")

        self.reply.assert_not_awaited()
        self.assertEqual(
            [call.args for call in self.set_finished.await_args_list],
            [(self.session_id, False)],
        )


if __name__ == "__main__":
    unittest.main()
