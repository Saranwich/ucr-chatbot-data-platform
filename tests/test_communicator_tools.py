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
        self.provider = patch.object(ai.typhoon, "chat_with_tools", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    async def test_บอกว่าจบแล้ว_ปัก_finished_แล้วตอบผู้ใช้(self):
        order = []

        async def remember_finished(session_id, value):
            order.append(f"finished:{value}")
            return True

        async def remember_reply(reply_token, messages):
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
        self.reply.assert_awaited_once_with("reply-token", ["ขอบคุณที่มาเล่าให้ฟังนะคะ"])
        self.assertEqual(order, ["finished:False", "line_reply", "finished:True"])

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
        )


if __name__ == "__main__":
    unittest.main()
