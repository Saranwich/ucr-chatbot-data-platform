"""ของใช้ร่วมของเทสต์ — ตัวปลอมแทนของจริงที่อยู่นอกแอป

เทสต์ทั้งหมดในโฟลเดอร์นี้ห้ามแตะ postgres / redis / typhoon / line ของจริง
ทุกตัวที่ออกไปข้างนอกถูกสับเป็นตัวปลอมก่อนเสมอ
"""

from unittest.mock import AsyncMock, patch


class FakeResponse:
    """คำตอบจาก httpx เท่าที่ clients/typhoon ใช้จริง — status_code / text / json()"""

    def __init__ (self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json (self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeAsyncClient:
    """ตัวแทน httpx.AsyncClient ที่คืนของที่เตรียมไว้ และจำ body ที่ถูกยิงไว้ให้ตรวจ"""

    def __init__ (self, response, recorder: dict):
        self._response = response
        self._recorder = recorder

    async def __aenter__ (self):
        return self

    async def __aexit__ (self, *args):
        return False

    async def post (self, url, headers=None, json=None):
        self._recorder["url"] = url
        self._recorder["headers"] = headers
        self._recorder["body"] = json
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def patch_log (module):
    """สับ psql.create_and_save_log ของโมดูลนั้นเป็นตัวปลอม คืน patcher ให้ไปเก็บ log ที่ถูกเขียน"""
    return patch.object(module.psql, "create_and_save_log", new=AsyncMock())
