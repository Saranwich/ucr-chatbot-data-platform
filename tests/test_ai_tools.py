"""services/ai_tools — schema ที่ยื่นให้โมเดล กับตัวลงมือทำตามที่โมเดลสั่ง

จุดที่ต้องแน่นที่สุดคือของเสียหนึ่งรายการต้องไม่ล้มทั้ง session
เพราะคนเรียกคือตัวกวาดหลังบ้าน พังเงียบ ๆ แล้วบทสนทนาหายไปทั้งรอบ
"""

import json
import unittest
from typing import get_args
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from app.schemas.report import Frequency, ProblemType, Threat
from app.services import ai_tools
from tests.support import patch_log

SESSION_ID = uuid4()


def tool_call (name: str, arguments) -> dict:
    """ปั้น tool call หน้าตาเดียวกับที่ typhoon คืนมา — arguments เป็นสตริง json"""
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)
    return {"id": "call_x", "type": "function", "function": {"name": name, "arguments": arguments}}


ONE_REPORT = {"reports": [{"title": "น้ำท่วมปากซอย", "type": "flood", "threat": "high"}]}


class SaveAnalyseToolSchemaTest (unittest.TestCase):
    """schema ต้องเดินตาม Report เสมอ หลุดเมื่อไหร่โมเดลกรอกค่าที่บันทึกไม่ได้"""

    def setUp (self):
        self.properties = ai_tools.SAVE_ANALYSE_TOOL["function"]["parameters"]["properties"]
        self.item = self.properties["reports"]["items"]["properties"]

    def test_เป็น_function_tool_ชื่อตรงกับฟังก์ชันจริง (self):
        self.assertEqual(ai_tools.SAVE_ANALYSE_TOOL["type"], "function")
        self.assertEqual(ai_tools.SAVE_ANALYSE_TOOL["function"]["name"], "save_analyse")
        self.assertIn("save_analyse", ai_tools.ANALYZER_TOOLS)

    def test_ไม่มี_session_id_ให้โมเดลเห็น (self):
        self.assertNotIn("session_id", self.properties)
        self.assertNotIn("session_id", self.item)
        self.assertNotIn("status", self.item)

    def test_ช่องครบตรงกับ_ReportDraft (self):
        self.assertEqual(set(self.item), set(ai_tools.ReportDraft.__annotations__))

    def test_enum_ตรงกับ_Literal_ใน_schema (self):
        for field, literal in (("type", ProblemType), ("threat", Threat), ("frequency", Frequency)):
            with self.subTest(field=field):
                self.assertEqual(self.item[field]["enum"], [*get_args(literal), None])

    def test_ทุกช่องเป็น_null_ได้ (self):
        """null = ยังไม่ได้ถาม บังคับให้กรอกครบเมื่อไหร่คือบังคับให้มันเดา"""
        self.assertEqual(ai_tools.SAVE_ANALYSE_TOOL["function"]["parameters"]["required"], ["reports"])
        for field, spec in self.item.items():
            with self.subTest(field=field):
                self.assertIn("null", spec["type"])


class CommunicatorToolTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.log = patch_log(ai_tools).start()
        self.set_finished = patch.object(
            ai_tools.psql, "set_session_finished", new=AsyncMock(return_value=True)
        ).start()
        self.addCleanup(patch.stopall)

    async def test_ยื่นสอง_tool_แต่ลงมือได้ตัวเดียว(self):
        """ปุ่มเป็นข้อมูลที่แนบมากับคำตอบ ไม่ใช่คำสั่งให้แอปไปทำอะไร จึงไม่มี handler"""
        tool = ai_tools.SET_FINISHED_FLAG_TOOL["function"]

        self.assertEqual(tool["name"], "set_finished_flag")
        self.assertEqual(tool["parameters"]["required"], ["is_finished"])
        self.assertEqual(
            [schema["function"]["name"] for schema in ai_tools.COMMUNICATOR_TOOL_SCHEMAS],
            ["set_finished_flag", "attach_quick_replies"],
        )
        self.assertEqual(set(ai_tools.COMMUNICATOR_TOOLS), {"set_finished_flag"})
        self.assertEqual(ai_tools.DATA_ONLY_TOOLS, frozenset({"attach_quick_replies"}))

    async def test_เจอ_tool_ปุ่มแล้วข้ามเงียบ_ไม่ฟ้องว่าไม่มีสิทธิ์(self):
        calls = [tool_call("attach_quick_replies", {"items": []})]

        executed = await ai_tools.run_communicator_tool_calls(SESSION_ID, calls)

        self.assertEqual(executed, 0)
        self.set_finished.assert_not_awaited()
        self.log.assert_not_awaited()

    async def test_เติม_session_id_แล้วปักธงจริง(self):
        calls = [tool_call("set_finished_flag", {"is_finished": True})]

        executed = await ai_tools.run_communicator_tool_calls(SESSION_ID, calls)

        self.assertEqual(executed, 1)
        self.set_finished.assert_awaited_once_with(SESSION_ID, True)

    async def test_is_finished_ไม่ใช่_boolean_ไม่แตะฐาน(self):
        calls = [tool_call("set_finished_flag", {"is_finished": "true"})]

        executed = await ai_tools.run_communicator_tool_calls(SESSION_ID, calls)

        self.assertEqual(executed, 0)
        self.set_finished.assert_not_awaited()

    async def test_tool_นอก_allowlist_เรียกไม่ได้(self):
        calls = [tool_call("save_analyse", ONE_REPORT)]

        executed = await ai_tools.run_communicator_tool_calls(SESSION_ID, calls)

        self.assertEqual(executed, 0)
        self.set_finished.assert_not_awaited()


class RunToolCallsTest (unittest.IsolatedAsyncioTestCase):
    def setUp (self):
        self.log = patch_log(ai_tools).start()
        self.save_report = patch.object(ai_tools.psql, "save_report", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    def saved_reports (self):
        return [call.args[0] for call in self.save_report.await_args_list]

    async def test_บันทึกหนึ่งรายงานสำเร็จ (self):
        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", ONE_REPORT)])

        self.assertEqual(outcome.saved, 1)
        self.assertTrue(outcome.is_success)
        report = self.saved_reports()[0]
        self.assertEqual(report.title, "น้ำท่วมปากซอย")
        self.assertEqual(report.type, "flood")
        self.assertEqual(report.session_id, SESSION_ID)
        self.assertEqual(report.status, "analyzed")

    async def test_หลายเรื่องในหนึ่ง_tool_call (self):
        arguments = {"reports": [{"title": "เรื่องแรก"}, {"title": "เรื่องสอง"}, {"title": "เรื่องสาม"}]}

        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", arguments)])

        self.assertEqual(outcome.saved, 3)
        self.assertEqual([r.title for r in self.saved_reports()], ["เรื่องแรก", "เรื่องสอง", "เรื่องสาม"])

    async def test_หลาย_tool_call_บันทึกได้หลายรายงาน (self):
        """โมเดลสั่งมาหลายครั้งในตาเดียวก็ต้องทำให้ครบทุกครั้ง ไม่ใช่เอาแต่ครั้งแรก"""
        calls = [
            tool_call("save_analyse", {"reports": [{"title": "เรื่องแรก"}]}),
            tool_call("save_analyse", {"reports": [{"title": "เรื่องสอง"}, {"title": "เรื่องสาม"}]}),
        ]

        outcome = await ai_tools.run_tool_calls(SESSION_ID, calls)

        self.assertEqual(outcome.saved, 3)
        self.assertEqual(len(self.saved_reports()), 3)

    async def test_ไม่มี_tool_call_เลย_คืนศูนย์ (self):
        outcome = await ai_tools.run_tool_calls(SESSION_ID, [])

        self.assertEqual(outcome.saved, 0)
        self.assertFalse(outcome.is_success)
        self.save_report.assert_not_awaited()

    async def test_tool_ที่ไม่อยู่ใน_allowlist_ถูกข้ามและ_log (self):
        calls = [
            tool_call("submit_resource_detail", {"image_id": str(uuid4()), "desc": "แอบเรียก"}),
            tool_call("save_analyse", ONE_REPORT),
        ]

        outcome = await ai_tools.run_tool_calls(SESSION_ID, calls)

        self.assertEqual(outcome.saved, 1)
        self.assertTrue(any("ไม่มีสิทธิ์เรียก" in call.args[1] for call in self.log.await_args_list))

    async def test_arguments_ไม่ใช่_json_ถูกข้ามและ_log (self):
        calls = [tool_call("save_analyse", "{เอ๊ะ ไม่ใช่ json"), tool_call("save_analyse", ONE_REPORT)]

        outcome = await ai_tools.run_tool_calls(SESSION_ID, calls)

        self.assertEqual(outcome.saved, 1)
        self.assertTrue(any("ไม่ใช่ json" in call.args[1] for call in self.log.await_args_list))

    async def test_arguments_เป็น_json_แต่ไม่ใช่ก้อนข้อมูล_ถูกข้าม (self):
        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", "[1, 2, 3]")])

        self.assertEqual(outcome.saved, 0)
        self.save_report.assert_not_awaited()

    async def test_session_id_ที่โมเดลกรอกมาถูกทิ้ง (self):
        """ปล่อยให้มันเลือก session เองเมื่อไหร่ คือปล่อยให้มันเขียนทับของคนอื่นด้วยการเดา id"""
        arguments = {"session_id": str(uuid4()), "reports": [{"title": "น้ำท่วม"}]}

        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", arguments)])

        self.assertEqual(outcome.saved, 1)
        self.assertEqual(self.saved_reports()[0].session_id, SESSION_ID)

    async def test_เรื่องที่ค่าไม่ผ่านตกไปเรื่องเดียว (self):
        """โมเดลพิมพ์ไทยมาในช่อง enum — เรื่องนั้นตก เรื่องที่เหลือยังต้องเก็บ"""
        arguments = {"reports": [{"title": "อันผิด", "type": "น้ำท่วม"}, {"title": "อันถูก", "type": "flood"}]}

        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", arguments)])

        self.assertEqual(outcome.saved, 1)
        self.assertEqual([r.title for r in self.saved_reports()], ["อันถูก"])

    async def test_arguments_ช่องแปลกปลอม_ไม่ล้มทั้ง_session (self):
        calls = [
            tool_call("save_analyse", {"reports": [], "ช่องที่ไม่มีจริง": 1}),
            tool_call("save_analyse", ONE_REPORT),
        ]

        outcome = await ai_tools.run_tool_calls(SESSION_ID, calls)

        self.assertEqual(outcome.saved, 1)

    async def test_tool_call_ผิดรูปทั้งก้อน_ไม่ล้มทั้ง_session (self):
        calls = ["ไม่ใช่ก้อนข้อมูล", {"ไม่มีช่อง function": True}, tool_call("save_analyse", ONE_REPORT)]

        outcome = await ai_tools.run_tool_calls(SESSION_ID, calls)

        self.assertEqual(outcome.saved, 1)


if __name__ == "__main__":
    unittest.main()


class ToolRunOutcomeTest (unittest.IsolatedAsyncioTestCase):
    """เส้นแบ่ง "วิเคราะห์เสร็จแล้ว" กับ "ต้องให้ลองใหม่" — ผิดข้างไหนก็เสียหายคนละแบบ

    ตัดสินว่าเสร็จทั้งที่ยังไม่เสร็จ = บทสนทนาหายไปโดยไม่มีรายงาน
    ตัดสินว่ายังไม่เสร็จทั้งที่เสร็จแล้ว = ได้รายงานซ้ำจากการลองใหม่
    """

    def setUp (self):
        self.log = patch_log(ai_tools).start()
        self.save_report = patch.object(ai_tools.psql, "save_report", new=AsyncMock()).start()
        self.addCleanup(patch.stopall)

    async def test_reports_ว่าง_ถือว่าสำเร็จ_ไม่ต้องลองใหม่ (self):
        """โมเดลอ่านแล้วบอกว่าไม่มีเรื่อง เป็นคำตอบที่ใช้ได้ ไม่ใช่ความล้มเหลว"""
        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", {"reports": []})])

        self.assertTrue(outcome.is_success)
        self.assertEqual((outcome.executed, outcome.failed, outcome.requested, outcome.saved), (1, 0, 0, 0))
        self.save_report.assert_not_awaited()

    async def test_ไม่มี_tool_call_เลย_ไม่สำเร็จ (self):
        """เงียบไม่ใช่คำตอบ กติกาคือต้องเรียก save_analyse เสมอ"""
        self.assertFalse((await ai_tools.run_tool_calls(SESSION_ID, [])).is_success)
        self.assertFalse((await ai_tools.run_tool_calls(SESSION_ID, None)).is_success)

    async def test_สั่งมาแต่กรอกผิดหมด_ไม่สำเร็จ (self):
        """executed ผ่านแต่ไม่เหลืออะไรลงฐาน แปลว่าโมเดลกรอกค่าผิด ให้มันเขียนใหม่"""
        arguments = {"reports": [{"type": "น้ำท่วม"}, {"type": "ร้อน"}]}

        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", arguments)])

        self.assertFalse(outcome.is_success)
        self.assertEqual((outcome.requested, outcome.saved), (2, 0))

    async def test_ฐานพัง_ไม่สำเร็จ (self):
        self.save_report.side_effect = RuntimeError("ต่อฐานไม่ได้")

        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", ONE_REPORT)])

        self.assertFalse(outcome.is_success)
        self.assertEqual((outcome.executed, outcome.failed, outcome.saved), (0, 1, 0))

    async def test_เก็บได้บางเรื่อง_ยังไม่สำเร็จ_ต้องลองใหม่ (self):
        """สั่งมา 2 เก็บได้ 1 แล้วปิดไปเลย เรื่องที่ตกจะไม่มีใครกลับมาเก็บอีกตลอดกาล

        ลองใหม่แล้วได้เรื่องแรกซ้ำ ยอมได้ ข้อมูลซ้ำมีคนมารวมทีหลังได้ ข้อมูลตกไม่มี
        """
        arguments = {"reports": [{"title": "อันถูก"}, {"type": "น้ำท่วม"}]}

        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", arguments)])

        self.assertFalse(outcome.is_success)
        self.assertEqual((outcome.requested, outcome.saved), (2, 1))

    async def test_เก็บได้ครบตามที่สั่ง_สำเร็จ (self):
        arguments = {"reports": [{"title": "เรื่องแรก"}, {"title": "เรื่องสอง"}]}

        outcome = await ai_tools.run_tool_calls(SESSION_ID, [tool_call("save_analyse", arguments)])

        self.assertTrue(outcome.is_success)
        self.assertEqual((outcome.requested, outcome.saved), (2, 2))

    async def test_มี_tool_ล้มปนมาแม้เก็บได้ครบ_ยังไม่สำเร็จ (self):
        """ตัวที่ล้มอาจเป็นเรื่องที่ยังไม่ได้เก็บ ปิดไปเลยคือทิ้งมันถาวร"""
        calls = [tool_call("save_analyse", ONE_REPORT), tool_call("save_analyse", "{พัง")]

        outcome = await ai_tools.run_tool_calls(SESSION_ID, calls)

        self.assertFalse(outcome.is_success)
        self.assertEqual((outcome.executed, outcome.failed, outcome.saved), (1, 1, 1))

    async def test_ชื่อ_tool_ที่ไม่รู้จักปนมา_ไม่สำเร็จ (self):
        calls = [tool_call("save_analyse", {"reports": []}), tool_call("ไม่รู้จัก", {})]

        outcome = await ai_tools.run_tool_calls(SESSION_ID, calls)

        self.assertFalse(outcome.is_success)
        self.assertEqual((outcome.executed, outcome.failed), (1, 1))
