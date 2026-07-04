import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routes.userdata import ProfileIn, _require_lineuser_id


# --- ProfileIn validation ----------------------------------------------------

def test_profile_in_accepts_full_profile():
    p = ProfileIn(nickname="ต้น", age_range="26–35", gender="ชาย", community="ตลาดเก่า")
    assert p.nickname == "ต้น"


def test_profile_in_rejects_missing_or_empty_fields():
    with pytest.raises(ValidationError):
        ProfileIn(nickname="ต้น", age_range="26–35", gender="ชาย")  # community missing
    with pytest.raises(ValidationError):
        ProfileIn(nickname="", age_range="26–35", gender="ชาย", community="ตลาดเก่า")


# --- auth: profile has no anonymous mode -------------------------------------

def test_require_lineuser_id_rejects_anonymous_with_401():
    # ไม่มี token (เปิดนอกแอป LINE) -> 401 ไม่ใช่ anonymous แบบ report form
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require_lineuser_id(None))
    assert exc.value.status_code == 401
