"""services/ai — ทางคุยของ communicator ต้องไม่ขยับ ทางของ analyzer ต้องแยก "พัง" กับ "ไม่มีเรื่อง" ให้ออก

None กับ [] หน้าตาคล้ายกันเวลาเขียนโค้ด แต่คนละความหมายคนละทางปิด session
เทสต์ในนี้ล็อกเส้นแบ่งนั้นไว้
"""

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.schemas.turn import Turn
from app.services import ai
from tests.support import patch_log

SESSION_ID = uuid4()
CONVERSATION = [
    Turn(role="user", content_type="text", content="หน้าบ้านน้ำท่วมทุกครั้งที่ฝนตก"),
    Turn(role="assistant", content_type="text", content="ท่วมสูงแค่ไหนคะ"),
]
TOOL_CALLS = [
    {"id": "call_1", "type": "function", "function": {"name": "save_analyse", "arguments": '{"reports": []}'}}
]


class AnalyzerTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.log = patch_log(ai).start()
        patch.object(ai.psql, "get_conversation", new=AsyncMock(return_value=CONVERSATION)).start()
        self.chat_with_tools = patch.object(ai.typhoon, "chat_with_tools", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    async def test_ส่ง_transcript_กับ_tool_ไปให้โมเดล (self):
        self.chat_with_tools.return_value = {"content": None, "tool_calls": TOOL_CALLS}

        await ai.analyzer(SESSION_ID)

        messages, tools = self.chat_with_tools.await_args.args[0], self.chat_with_tools.await_args.args[1]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIn("ชาวบ้าน: หน้าบ้านน้ำท่วมทุกครั้งที่ฝนตก", messages[-1]["content"])
        self.assertEqual([tool["function"]["name"] for tool in tools], ["save_analyse"])

    async def test_เติมกติกาการเรียก_tool_ต่อท้าย_prompt_เสมอ (self):
        """prompt จาก db อาจเป็นของเก่าที่ไม่รู้จัก tool calling โค้ดต้องเป็นคนเติมกติกาให้เอง"""
        stale = ai.ai_config.get()
        stale_analyzer = stale.analyzer.model_copy(update={"prompt": "สรุปบทสนทนาเป็นข้อความให้ทีมอ่าน"})
        patch.object(ai.ai_config, "get", return_value=stale.model_copy(update={"analyzer": stale_analyzer})).start()
        self.chat_with_tools.return_value = {"content": None, "tool_calls": TOOL_CALLS}

        await ai.analyzer(SESSION_ID)

        system = self.chat_with_tools.await_args.args[0][0]["content"]
        self.assertIn("สรุปบทสนทนาเป็นข้อความให้ทีมอ่าน", system)
        self.assertIn(ai.SAVE_ANALYSE_PROTOCOL, system)

    async def test_ไม่มี_prompt_ใน_config_ก็ยังมีกติกา (self):
        empty = ai.ai_config.get()
        empty_analyzer = empty.analyzer.model_copy(update={"prompt": ""})
        patch.object(ai.ai_config, "get", return_value=empty.model_copy(update={"analyzer": empty_analyzer})).start()
        self.chat_with_tools.return_value = {"content": None, "tool_calls": TOOL_CALLS}

        await ai.analyzer(SESSION_ID)

        messages = self.chat_with_tools.await_args.args[0]
        self.assertEqual(messages[0]["content"], ai.SAVE_ANALYSE_PROTOCOL)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])

    async def test_คืน_tool_calls_ดิบ_ไม่ลงมือทำเอง (self):
        self.chat_with_tools.return_value = {"content": None, "tool_calls": TOOL_CALLS}

        with patch.object(ai.psql, "save_report", new=AsyncMock()) as save_report:
            tool_calls, config = await ai.analyzer(SESSION_ID)

        self.assertEqual(tool_calls, TOOL_CALLS)
        self.assertEqual(config.agent, "analyzer")
        save_report.assert_not_awaited()

    async def test_provider_ไม่ตอบ_คืน_None (self):
        self.chat_with_tools.return_value = None

        tool_calls, _ = await ai.analyzer(SESSION_ID)

        self.assertIsNone(tool_calls)

    async def test_ตอบแต่ไม่มี_tool_calls_คืนลิสต์ว่าง (self):
        """[] คือ "อ่านแล้วไม่มีเรื่อง" ต้องไม่ใช่ None ไม่งั้น session จะถูกวนวิเคราะห์ใหม่ไม่จบ"""
        self.chat_with_tools.return_value = {"content": "ไม่มีเรื่องสภาพพื้นที่ในบทสนทนานี้"}

        tool_calls, _ = await ai.analyzer(SESSION_ID)

        self.assertEqual(tool_calls, [])
        self.assertIsNotNone(tool_calls)

    async def test_tool_calls_เป็น_null_ก็นับเป็นลิสต์ว่าง (self):
        self.chat_with_tools.return_value = {"content": "", "tool_calls": None}

        tool_calls, _ = await ai.analyzer(SESSION_ID)

        self.assertEqual(tool_calls, [])

    async def test_tool_calls_ผิดชนิด_คืน_None (self):
        """อ่านไม่ออกคือยังไม่ได้วิเคราะห์ ต้องได้ลองใหม่ ไม่ใช่ปิดทิ้ง"""
        self.chat_with_tools.return_value = {"tool_calls": "save_analyse"}

        tool_calls, _ = await ai.analyzer(SESSION_ID)

        self.assertIsNone(tool_calls)

    async def test_ไม่มีบทสนทนาในฐาน_คืน_None_ไม่เรียกโมเดล (self):
        patch.object(ai.psql, "get_conversation", new=AsyncMock(return_value=[])).start()

        tool_calls, _ = await ai.analyzer(SESSION_ID)

        self.assertIsNone(tool_calls)
        self.chat_with_tools.assert_not_awaited()

    async def test_provider_ที่ยังไม่รองรับ_คืน_None_ไม่เรียกโมเดล (self):
        config = ai.ai_config.get()
        analyzer_config = config.analyzer.model_copy(update={"provider": "openai"})
        patch.object(ai.ai_config, "get", return_value=config.model_copy(update={"analyzer": analyzer_config})).start()

        tool_calls, _ = await ai.analyzer(SESSION_ID)

        self.assertIsNone(tool_calls)
        self.chat_with_tools.assert_not_awaited()


class CommunicatorReplyTest (unittest.IsolatedAsyncioTestCase):
    """communicator ยิงรอบเดียวจบ ได้ JSON ก้อนเดียวที่มีครบทั้งข้อความ ธงจบ และปุ่ม"""

    def setUp (self):
        self.log = patch_log(ai).start()
        self.chat_with_tools = patch.object(ai.typhoon, "chat_with_tools", new=AsyncMock()).start()
        self.chat = patch.object(
            ai.typhoon,
            "chat",
            new=AsyncMock(return_value='{"reply_text": "สวัสดีค่ะ", "is_finished": false, "quick_replies": []}'),
        ).start()
        self.addCleanup(patch.stopall)

    async def test_ยิงรอบเดียวได้คำตอบที่แกะแล้วกับ_config (self):
        reply, config = await ai.communicator_reply(CONVERSATION)

        self.assertEqual(reply.reply_text, "สวัสดีค่ะ")
        self.assertFalse(reply.is_finished)
        self.assertEqual(reply.quick_replies, [])
        self.assertEqual(config.agent, "communicator")
        self.assertEqual(self.chat.await_count, 1)

    async def test_ไม่แตะทาง_tool_calling_อีกแล้ว (self):
        """ยิงรอบสองคือการป้อนผลที่เราปั้นเองกลับเข้าไป ตัดทิ้งทั้งเส้นแล้ว"""
        await ai.communicator_reply(CONVERSATION)

        self.chat_with_tools.assert_not_awaited()

    async def test_เติมสัญญารูปคำตอบต่อท้าย_prompt_เสมอ (self):
        """prompt ในฐานอาจเก่ากว่ารูปที่โค้ดรออยู่ โค้ดต้องเป็นคนเติมสัญญาให้เอง"""
        await ai.communicator_reply(CONVERSATION)

        system = self.chat.await_args.args[0][0]["content"]
        self.assertIn(ai.COMMUNICATOR_OUTPUT_CONTRACT, system)

    async def test_ขอ_response_format_ไปด้วยทุกครั้ง (self):
        """typhoon ทิ้งช่องนี้ แต่เจ้าที่บังคับตามจริงมีอยู่ ส่งไปไม่มีต้นทุน"""
        await ai.communicator_reply(CONVERSATION)

        self.assertEqual(self.chat.await_args.kwargs["response_format"], ai.RESPONSE_FORMAT)

    async def test_ตาของบอทในประวัติถูกเขียนกลับเป็น_JSON (self):
        """โมเดลลอกรูปจากตาเก่าของตัวเอง เห็นร้อยแก้วเมื่อไหร่มันเลิกคาย JSON ทั้งบทสนทนา

        วัดบนบทสนทนาจริง 14 ตา: ประวัติเป็นร้อยแก้วได้ JSON 4/24 ประวัติเป็น JSON ได้ 24/24
        """
        import json

        await ai.communicator_reply(CONVERSATION)

        messages = self.chat.await_args.args[0]
        user_turn, bot_turn = messages[1], messages[2]

        self.assertEqual(user_turn["content"], "หน้าบ้านน้ำท่วมทุกครั้งที่ฝนตก")
        self.assertEqual(
            json.loads(bot_turn["content"]),
            {"reply_text": "ท่วมสูงแค่ไหนคะ", "is_finished": False, "quick_replies": []},
        )

    async def test_ส่งบทสนทนาเป็นหลายตาเหมือนเดิม (self):
        """analyzer ยุบเป็นก้อนเดียว แต่ communicator ต้องยังส่งทีละตา"""
        await ai.communicator_reply(CONVERSATION)

        messages = self.chat.await_args.args[0]
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant"])

    async def test_โมเดลไม่ตอบ_คืน_None (self):
        self.chat.return_value = None

        reply, config = await ai.communicator_reply(CONVERSATION)

        self.assertIsNone(reply)
        self.assertEqual(config.agent, "communicator")

    async def test_provider_ที่ยังไม่รองรับ_ไม่เรียกโมเดล (self):
        config = ai.ai_config.get()
        communicator = config.communicator.model_copy(update={"provider": "openai"})
        patch.object(ai.ai_config, "get", return_value=config.model_copy(update={"communicator": communicator})).start()

        reply, _ = await ai.communicator_reply(CONVERSATION)

        self.assertIsNone(reply)
        self.chat.assert_not_awaited()

    async def test_โมเดลลืมรูปคายร้อยแก้วมา_ยังได้ตอบชาวบ้าน (self):
        """วัดจากของจริงแล้วเจอ 2/72 ครั้ง — ทั้งสองครั้งเป็นคำตอบที่ใช้ได้ ห้ามทิ้ง"""
        self.chat.return_value = "ขอบคุณค่ะ น้ำท่วมที่นั่นบ่อยไหมคะ"

        reply, _ = await ai.communicator_reply(CONVERSATION)

        self.assertEqual(reply.reply_text, "ขอบคุณค่ะ น้ำท่วมที่นั่นบ่อยไหมคะ")
        self.assertFalse(reply.is_finished)


if __name__ == "__main__":
    unittest.main()
