"""คุยกับโมเดล — **ไฟล์เดียวในโปรเจกต์ที่รู้ว่าเราใช้เจ้าไหน**

ตอนนี้เป็น Gemini แต่ต่อผ่าน**ช่องทางที่พูดภาษา OpenAI** ของ Google เอง
(`.../v1beta/openai/`) เลยใช้ไลบรารี `openai` ได้ตรง ๆ ทั้ง tool calling
และ `reasoning_effort` — ไม่ต้องมีโค้ดแปลงร่างให้ใครดูแล

ที่ไม่ใช้ REST ดั้งเดิมของ Google (`models/<model>:generateContent`) เพราะรูปร่าง
ข้อความมันคนละแบบ ถ้าใช้อันนั้น `services/survey.py` ที่ส่ง messages/tools
แบบ OpenAI มาจะต้องถูกรื้อตาม ทั้งที่มันไม่ควรต้องรู้เลยว่าปลายทางเป็นเจ้าไหน

วันเปลี่ยนเจ้า: แก้ MODEL กับ base_url ตรงนี้ที่เดียว
"""

import json

from openai import AsyncOpenAI
from app.core.config import API_ENDPOINT, API_KEY

# ชื่อโมเดลอยู่ที่เดียว เดิมพิมพ์ซ้ำ 3 ที่ แล้ววันเปลี่ยนก็ลืมที่ใดที่หนึ่งเสมอ
#
# **ที่ใช้ lite เพราะโควตา ไม่ใช่เพราะมันดีกว่า** — key ฟรีให้ `gemini-flash-latest`
# แค่ 20 ครั้ง/วัน/โปรเจกต์ ซึ่งหมดตั้งแต่ยังทดสอบไม่ทันจบ (หนึ่งตาของบทสนทนา
# กินได้ถึง 3 ครั้ง เพราะวนเรียก tool ได้ 3 รอบ — ดู MAX_TOOL_ROUNDS)
# วันเปิดบิลแล้วค่อยเปลี่ยนกลับเป็น gemini-flash-latest ตรงนี้บรรทัดเดียว
MODEL = "gemini-flash-lite-latest"

# คิดหนักหน่อยได้ ตาหนึ่งของบทสนทนาไม่ได้เกิดถี่ขนาดต้องประหยัด
# และของที่เราขอจากมันคือการ**ไม่ปั้นเรื่องที่ชาวบ้านไม่ได้พูด** ซึ่งพลาดแล้วแพง
EFFORT = {"reasoning_effort": "high"}

client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=API_ENDPOINT,
)


async def get_playground(message: str) -> str:
    """ยิงเข้าโมเดลตรง ๆ ไม่มีความจำ ไม่มีเครื่องมือ — ไว้เช็คว่า key กับ endpoint ใช้ได้"""

    completion = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": message}],
        extra_body=EFFORT,
    )

    return completion.choices[0].message.content


async def chat(messages: list[dict]) -> str:
    """Same model as the playground, but takes a full message history."""

    completion = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        extra_body=EFFORT,
    )

    return completion.choices[0].message.content


async def chat_tools(messages: list[dict], tools: list[dict]) -> dict:
    """Chat, letting the model call our tools.

    Returns a plain dict so nothing outside this file has to know what an
    OpenAI object looks like:

        {"content": "...", "tool_calls": [{"id", "name", "arguments": {...}}]}
    """

    completion = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        extra_body=EFFORT,
    )

    message = completion.choices[0].message
    return {
        "content": message.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "name": call.function.name,
                "arguments": json.loads(call.function.arguments or "{}"),
            }
            for call in (message.tool_calls or [])
        ],
    }


def tool_exchange(tool_calls: list[dict], result: str) -> list[dict]:
    """The two messages the model expects back after it called a tool:
    what it asked for, and what it got. Same `result` for every call."""

    asked = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                },
            }
            for call in tool_calls
        ],
    }
    got = [
        {"role": "tool", "tool_call_id": call["id"], "content": result}
        for call in tool_calls
    ]
    return [asked] + got
