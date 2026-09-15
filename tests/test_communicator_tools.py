"""เส้นทาง communicator tool calling — ชาวบ้านบอกว่าจบแล้วต้องปัก session ก่อนตอบกลับ"""

import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.schemas.turn import Turn
from app.schemas.user import User
from app.services import ai, chatbot


class CommunicatorFinishedFlagTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
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
        self.provider = patch.object(ai.typhoon, "chat_with_tools", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    async def test_บอกว่าจบแล้ว_ปัก_finished_แล้วตอบผู้ใช้(self):
        order = []

        async def remember_finished(session_id, value):
            order.append(f"finished:{value}")
            return True

        async def remember_reply(reply_token, messages, quick_replies=None):
            order.append("line_reply")

        self.set_finished.side_effect = remember_finished
        self.reply.side_effect = remember_reply
        tool_call = {
            "id": "finish_1",
            "type": "function",
            "function": {
                "name": "set_finished_flag",
                "arguments": json.dumps({"is_finished": True}),
            },
        }
        self.provider.side_effect = [
            {"role": "assistant", "content": None, "tool_calls": [tool_call]},
            {"role": "assistant", "content": "ขอบคุณที่มาเล่าให้ฟังนะคะ", "tool_calls": []},
        ]

        await chatbot.handle_user_events(
            "U-test",
            [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "message": {"type": "text", "text": "จบแล้วครับ"},
                }
            ],
        )

        self.assertEqual(
            [call.args for call in self.set_finished.await_args_list],
            [(self.session_id, False), (self.session_id, True)],
        )
        self.assertEqual(self.provider.await_count, 2)
        self.reply.assert_awaited_once_with(
            "reply-token", ["ขอบคุณที่มาเล่าให้ฟังนะคะ"], quick_replies=[]
        )
        self.assertEqual(order, ["finished:False", "line_reply", "finished:True"])

    async def test_ขึ้นจุดโหลดก่อนถามโมเดล(self):
        """จุดต้องขึ้นก่อนช่วงที่รอนาน ขึ้นหลังตอบไปแล้วก็ไม่มีประโยชน์"""
        order = []

        async def remember_loading(line_user_id):
            order.append(f"loading:{line_user_id}")

        async def remember_provider(*args, **kwargs):
            order.append("provider")
            return {"role": "assistant", "content": "สวัสดีค่ะ", "tool_calls": []}

        self.loading.side_effect = remember_loading
        self.provider.side_effect = remember_provider

        await chatbot.handle_user_events(
            "U-test",
            [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "message": {"type": "text", "text": "สวัสดีครับ"},
                }
            ],
        )

        self.assertEqual(order, ["loading:U-test", "provider"])

    async def test_provider_ไม่เรียก_tool_ยังตอบผู้ใช้และคง_finished_false(self):
        self.provider.return_value = {
            "role": "assistant",
            "content": "สวัสดีค่ะ มีเรื่องสภาพพื้นที่อยากเล่าไหมคะ",
            "tool_calls": [],
        }

        await chatbot.handle_user_events(
            "U-test",
            [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "message": {"type": "text", "text": "อ้าว ทำไมเงียบ"},
                }
            ],
        )

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

    async def test_communicator_ขอปุ่มแชร์พิกัด_แล้วส่ง_location_action_ไป_LINE(self):
        button_call = {
            "id": "buttons_1",
            "type": "function",
            "function": {
                "name": "attach_quick_replies",
                "arguments": json.dumps(
                    {"items": [{"type": "location", "label": "แชร์พิกัด", "text": None}]},
                    ensure_ascii=False,
                ),
            },
        }
        self.provider.return_value = {
            "role": "assistant",
            "content": "ช่วยแชร์พิกัดจุดที่น้ำท่วมได้ไหมคะ",
            "tool_calls": [button_call],
        }

        await chatbot.handle_user_events(
            "U-test",
            [{
                "type": "message",
                "replyToken": "reply-token",
                "message": {"type": "text", "text": "ฝนตกแล้วน้ำท่วมค่ะ"},
            }],
        )

        self.reply.assert_awaited_once_with(
            "reply-token",
            ["ช่วยแชร์พิกัดจุดที่น้ำท่วมได้ไหมคะ"],
            quick_replies=[
                {"type": "location", "label": "แชร์พิกัด", "text": None}
            ],
        )
        # แปะปุ่มอย่างเดียว ไม่ได้แตะธงจบ — เหลือแค่ครั้งที่ chatbot ถอนให้ตอนรับข้อความ
        self.assertEqual(
            [call.args for call in self.set_finished.await_args_list],
            [(self.session_id, False)],
        )

    async def test_เรียกสอง_tool_ในตาเดียว_ได้ทั้งปุ่มและธงจบ(self):
        """แยก tool แล้วสองคำสั่งในตาเดียวเป็นเรื่องปกติ ไม่ใช่ความผิดพลาดอีกต่อไป"""
        self.provider.return_value = {
            "role": "assistant",
            "content": "ขอบคุณที่เล่าให้ฟังนะคะ",
            "tool_calls": [
                {
                    "id": "finish_1",
                    "type": "function",
                    "function": {
                        "name": "set_finished_flag",
                        "arguments": json.dumps({"is_finished": True}),
                    },
                },
                {
                    "id": "buttons_1",
                    "type": "function",
                    "function": {
                        "name": "attach_quick_replies",
                        "arguments": json.dumps(
                            {"items": [
                                {"type": "message", "label": "มีอีกเรื่อง", "text": "มีอีกเรื่อง"},
                                {"type": "message", "label": "พอแล้ว", "text": "พอแล้ว"},
                            ]},
                            ensure_ascii=False,
                        ),
                    },
                },
            ],
        }

        await chatbot.handle_user_events(
            "U-test",
            [{
                "type": "message",
                "replyToken": "reply-token",
                "message": {"type": "text", "text": "พอแค่นี้ครับ"},
            }],
        )

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


if __name__ == "__main__":
    unittest.main()
