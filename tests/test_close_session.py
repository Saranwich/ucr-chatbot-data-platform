"""services/chatbot.close_session — ทางปิด session กับการลงมือบันทึกตามที่ analyzer สั่ง

หัวใจของไฟล์นี้คือ "พังต้องได้ลองใหม่ ไม่พังต้องปิดให้จบ" และต้องเลิกลองเมื่อครบโควตา
ปิดผิดทางฝั่งหนึ่งคือบทสนทนาหาย อีกฝั่งคือ session วนวิเคราะห์ใหม่ไม่จบ
"""

import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from pydantic import ValidationError

from app.schemas.report import Report, Session
from app.services import ai_tools, chatbot
from tests.support import patch_log

USER_ID = uuid4()
SESSION = Session(user_id=USER_ID)
REDIS_KEY = f"session:{USER_ID}"
RAW_REDIS = json.dumps({"session_id": str(SESSION.id), "turns": []})

TOOL_CALLS = [
    {
        "id": "call_1",
        "type": "function",
        "function": {"name": "save_analyse", "arguments": '{"reports": [{"title": "น้ำท่วมปากซอย"}]}'},
    }
]

SAVED_ONE = ai_tools.ToolRunOutcome(executed=1, failed=0, requested=1, saved=1)
NO_STORY = ai_tools.ToolRunOutcome(executed=1, failed=0, requested=0, saved=0)
ALL_INVALID = ai_tools.ToolRunOutcome(executed=1, failed=0, requested=2, saved=0)
PARTIAL = ai_tools.ToolRunOutcome(executed=1, failed=0, requested=2, saved=1)
DB_DOWN = ai_tools.ToolRunOutcome(executed=0, failed=1, requested=0, saved=0)
NOTHING_RAN = ai_tools.ToolRunOutcome(executed=0, failed=0, requested=0, saved=0)


class CloseSessionTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.log = patch_log(chatbot).start()
        patch.object(chatbot.redis, "get_session", new=AsyncMock(return_value=RAW_REDIS)).start()
        self.delete_session = patch.object(chatbot.redis, "delete_session", new=AsyncMock()).start()
        patch.object(chatbot.psql, "get_session", new=AsyncMock(return_value=SESSION)).start()
        self.set_status = patch.object(chatbot.psql, "set_session_status", new=AsyncMock()).start()
        self.analyzer = patch.object(chatbot.ai, "analyzer", new=AsyncMock()).start()
        self.run_tool_calls = patch.object(chatbot.ai_tools, "run_tool_calls", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    def statuses (self):
        return [call.args[1] for call in self.set_status.await_args_list]

    def logs (self):
        return [call.args[1] for call in self.log.await_args_list]

    def analyzer_returns (self, *tool_calls_per_attempt):
        self.analyzer.side_effect = [(calls, None) for calls in tool_calls_per_attempt]

    def tools_return (self, *outcome_per_attempt):
        self.run_tool_calls.side_effect = list(outcome_per_attempt)

    async def test_สำเร็จตั้งแต่ครั้งแรก_ไม่ลองซ้ำ (self):
        self.analyzer_returns(TOOL_CALLS)
        self.tools_return(SAVED_ONE)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertEqual(saved, 1)
        self.assertEqual(self.analyzer.await_count, 1)
        self.run_tool_calls.assert_awaited_once_with(SESSION.id, TOOL_CALLS)
        self.assertEqual(self.statuses(), ["pending", "analyzed"])
        self.delete_session.assert_awaited_once_with(REDIS_KEY)

    async def test_ล้มสองครั้งแล้วสำเร็จครั้งที่สาม (self):
        """แต่ละครั้งต้องเรียก analyzer ใหม่ทั้งรอบ ไม่ใช่ยิงคำสั่งชุดเดิมซ้ำ"""
        self.analyzer_returns(None, TOOL_CALLS, TOOL_CALLS)
        self.tools_return(ALL_INVALID, SAVED_ONE)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertEqual(saved, 1)
        self.assertEqual(self.analyzer.await_count, 3)
        self.assertEqual(self.run_tool_calls.await_count, 2)
        self.assertEqual(self.statuses(), ["pending", "analyzed"])
        self.delete_session.assert_awaited_once_with(REDIS_KEY)

    async def test_ไม่เรียก_tool_เลยครบสามครั้ง_เลิกลอง (self):
        """โมเดลตอบเป็น prose ทุกครั้ง — ลิสต์ว่างจาก analyzer คือผิดกติกา ไม่ใช่ "ไม่มีเรื่อง" """
        self.analyzer_returns([], [], [])
        self.tools_return(NOTHING_RAN, NOTHING_RAN, NOTHING_RAN)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertIsNone(saved)
        self.assertEqual(self.analyzer.await_count, chatbot.ANALYSER_MAX_ATTEMPTS)
        self.assertNotIn("analyzed", self.statuses())

    async def test_ฐานพังครบสามครั้ง_เลิกลอง (self):
        self.analyzer_returns(TOOL_CALLS, TOOL_CALLS, TOOL_CALLS)
        self.tools_return(DB_DOWN, DB_DOWN, DB_DOWN)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertIsNone(saved)
        self.assertEqual(self.run_tool_calls.await_count, chatbot.ANALYSER_MAX_ATTEMPTS)
        self.assertNotIn("analyzed", self.statuses())

    async def test_provider_ไม่ตอบครบสามครั้ง_เลิกลอง (self):
        self.analyzer_returns(None, None, None)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertIsNone(saved)
        self.assertEqual(self.analyzer.await_count, chatbot.ANALYSER_MAX_ATTEMPTS)
        self.run_tool_calls.assert_not_awaited()

    async def test_ครบโควตาแล้ว_ปักเป็น_analysis_failed_และลบ_redis (self):
        """analyzed คือโกหกว่ามีคนอ่านแล้ว not_analyzed คือปนกับของที่ยังไม่ถึงคิว ต้องเป็นป้ายของตัวเอง"""
        self.analyzer_returns(None, None, None)

        await chatbot.close_session(REDIS_KEY)

        self.assertEqual(self.statuses()[-1], "analysis_failed")
        self.assertNotIn("analyzed", self.statuses())
        self.assertNotIn("not_analyzed", self.statuses())
        self.delete_session.assert_awaited_once_with(REDIS_KEY)
        self.assertTrue(any("ANALYSIS_FAILED" in entry for entry in self.logs()))

    async def test_analysis_failed_ผ่าน_schema_ของ_session (self):
        """ค่าที่เขียนลงฐานต้องเป็นค่าที่ Session ยอมรับจริง ไม่ใช่สตริงที่พิมพ์ถูกโดยบังเอิญ"""
        self.assertEqual(SESSION.model_copy(update={"status": "analysis_failed"}).status, "analysis_failed")
        self.assertEqual(
            Session.model_validate({"user_id": USER_ID, "status": "analysis_failed"}).status, "analysis_failed"
        )

    async def test_report_ไม่รับ_analysis_failed (self):
        """สถานะนี้เป็นของ session เท่านั้น report เกิดได้ก็ต่อเมื่อวิเคราะห์สำเร็จแล้ว"""
        with self.assertRaises(ValidationError):
            Report(session_id=SESSION.id, status="analysis_failed")

    async def test_session_ที่ล้มถาวรแล้ว_ตัวกวาดไม่หยิบซ้ำ (self):
        """ถ้า redis key โผล่มาอีกด้วยเหตุใดก็ตาม ต้องไม่ถูกลากไปวิเคราะห์ใหม่"""
        patch.object(
            chatbot.psql,
            "get_session",
            new=AsyncMock(return_value=SESSION.model_copy(update={"status": "analysis_failed"})),
        ).start()

        self.assertIsNone(await chatbot.close_session(REDIS_KEY))
        self.analyzer.assert_not_awaited()
        self.set_status.assert_not_awaited()

    async def test_เก็บได้ไม่ครบ_ต้องลองใหม่_ไม่ปิดทิ้ง (self):
        """สั่งมา 2 เก็บได้ 1 แล้วปิด = เรื่องที่ตกหายถาวร ยอมให้ซ้ำจากการลองใหม่ดีกว่า"""
        self.analyzer_returns(TOOL_CALLS, TOOL_CALLS)
        self.tools_return(PARTIAL, SAVED_ONE)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertEqual(saved, 1)
        self.assertEqual(self.analyzer.await_count, 2)
        self.assertEqual(self.statuses(), ["pending", "analyzed"])

    async def test_เก็บได้ไม่ครบทั้งสามครั้ง_ปักเป็น_analysis_failed (self):
        self.analyzer_returns(TOOL_CALLS, TOOL_CALLS, TOOL_CALLS)
        self.tools_return(PARTIAL, PARTIAL, PARTIAL)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertIsNone(saved)
        self.assertEqual(self.statuses()[-1], "analysis_failed")

    async def test_ไม่มีเรื่องให้บันทึก_ถือว่าสำเร็จและเรียกครั้งเดียว (self):
        """reports=[] คือคำตอบที่ใช้ได้ ปิดให้จบ ห้ามลองใหม่เพราะรอบหน้าก็ได้คำตอบเดิม"""
        self.analyzer_returns(TOOL_CALLS)
        self.tools_return(NO_STORY)

        saved = await chatbot.close_session(REDIS_KEY)

        self.assertEqual(saved, 0)
        self.assertIsNotNone(saved)
        self.assertEqual(self.analyzer.await_count, 1)
        self.assertEqual(self.statuses(), ["pending", "analyzed"])
        self.delete_session.assert_awaited_once_with(REDIS_KEY)

    async def test_redis_หมดอายุไปก่อนแล้ว_ไม่ทำอะไรต่อ (self):
        patch.object(chatbot.redis, "get_session", new=AsyncMock(return_value=None)).start()

        self.assertIsNone(await chatbot.close_session(REDIS_KEY))
        self.analyzer.assert_not_awaited()
        self.set_status.assert_not_awaited()

    async def test_มีคนวิเคราะห์อยู่แล้ว_ข้ามไป (self):
        """กันตัวกวาดสองรอบซ้อนหยิบ session เดียวกันไปวิเคราะห์พร้อมกัน"""
        patch.object(
            chatbot.psql, "get_session", new=AsyncMock(return_value=SESSION.model_copy(update={"status": "pending"}))
        ).start()

        self.assertIsNone(await chatbot.close_session(REDIS_KEY))
        self.analyzer.assert_not_awaited()
        self.set_status.assert_not_awaited()
        self.delete_session.assert_not_awaited()


class SweepOnceWiringTest (unittest.IsolatedAsyncioTestCase):
    """ต่อสายจริงตั้งแต่ตัวกวาดถึง reports — ใครเรียกใครถูกลำดับไหม

    ไม่สับ close_session/analyzer/run_tool_calls ในชั้นนี้ สับแค่ของนอกแอป
    จะได้จับได้ตอนมีคนย้ายงานข้ามชั้นแล้วชั้นกลางหลุดหาย
    """

    def setUp (self):
        from app.services import ai, ai_tools, runtime

        self.runtime = runtime
        patch_log(runtime).start()
        patch_log(chatbot).start()
        patch_log(ai).start()
        patch_log(ai_tools).start()

        patch.object(runtime.redis, "scan_session_keys", new=AsyncMock(return_value=[REDIS_KEY])).start()
        patch.object(runtime.redis, "get_ttl", new=AsyncMock(return_value=10)).start()
        patch.object(chatbot.redis, "get_session", new=AsyncMock(return_value=RAW_REDIS)).start()
        patch.object(chatbot.redis, "delete_session", new=AsyncMock()).start()
        patch.object(chatbot.psql, "get_session", new=AsyncMock(return_value=SESSION)).start()
        self.set_status = patch.object(chatbot.psql, "set_session_status", new=AsyncMock()).start()

        patch.object(
            ai.psql,
            "get_conversation",
            new=AsyncMock(return_value=[ai.Turn(role="user", content_type="text", content="น้ำท่วมปากซอย")]),
        ).start()
        self.chat_with_tools = patch.object(ai.typhoon, "chat_with_tools", new=AsyncMock()).start()
        self.save_report = patch.object(ai_tools.psql, "save_report", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    async def test_โมเดลสั่งบันทึก_เรื่องลงฐานจริงและ_session_ปิด (self):
        self.chat_with_tools.return_value = {"content": None, "tool_calls": TOOL_CALLS}

        closed = await self.runtime.sweep_once()

        self.assertEqual(closed, 1)
        self.save_report.assert_awaited_once()
        report = self.save_report.await_args.args[0]
        self.assertEqual(report.title, "น้ำท่วมปากซอย")
        self.assertEqual(report.session_id, SESSION.id)
        self.assertEqual(report.status, "analyzed")
        self.assertEqual([call.args[1] for call in self.set_status.await_args_list], ["pending", "analyzed"])

    async def test_provider_ล้มทุกครั้ง_ลองครบสามแล้วเลิก_ไม่มีรายงาน (self):
        self.chat_with_tools.return_value = None

        closed = await self.runtime.sweep_once()

        self.assertEqual(closed, 0)
        self.assertEqual(self.chat_with_tools.await_count, chatbot.ANALYSER_MAX_ATTEMPTS)
        self.save_report.assert_not_awaited()
        self.assertEqual([call.args[1] for call in self.set_status.await_args_list], ["pending", "analysis_failed"])

    async def test_โมเดลกรอกผิดครั้งแรก_ครั้งที่สองเก็บได้_ลงฐานหนึ่งเรื่อง (self):
        """retry เดินครบเส้นจริง ตั้งแต่ยิงโมเดลใหม่ ยันแถวลง reports"""
        bad = [{"id": "c1", "type": "function",
                "function": {"name": "save_analyse", "arguments": '{"reports": [{"type": "น้ำท่วม"}]}'}}]
        self.chat_with_tools.side_effect = [
            {"content": None, "tool_calls": bad},
            {"content": None, "tool_calls": TOOL_CALLS},
        ]

        closed = await self.runtime.sweep_once()

        self.assertEqual(closed, 1)
        self.assertEqual(self.chat_with_tools.await_count, 2)
        self.save_report.assert_awaited_once()
        self.assertEqual(self.save_report.await_args.args[0].title, "น้ำท่วมปากซอย")
        self.assertEqual([call.args[1] for call in self.set_status.await_args_list], ["pending", "analyzed"])


if __name__ == "__main__":
    unittest.main()
