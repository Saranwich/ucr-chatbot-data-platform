"""ข้อมูลส่วนตัว (Userdata LIFF) — profile page + get/save profile.

Profile (nickname / age_range / gender / community) อยู่เป็นคอลัมน์บนตาราง users
ที่เดียว และแก้ไขผ่านหน้านี้ทางเดียว — survey ไม่ถามอีกแล้ว

Auth แบบเดียวกับ report form: LIFF access token ใน Authorization header
verify กับ LINE เพื่อได้ lineuser_id ที่เชื่อถือได้ ต่างกันตรงที่หน้านี้
**ไม่มีโหมด anonymous** — ไม่รู้ว่าเป็นใครก็ไม่มีแถวให้แก้ (401)

Thin route — profile DB logic lives in services/user.py.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import EDIT_PROFILE_ID
from app.database import get_db
from app.utils.liff_auth import resolve_lineuser_id
from app.services import user as user_service

router = APIRouter(tags=["userdata"])

_HTML_FILE = Path(__file__).resolve().parent.parent / "static" / "userdata_form.html"


class ProfileIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=100)
    age_range: str = Field(min_length=1, max_length=50)
    gender: str = Field(min_length=1, max_length=50)
    community: str = Field(min_length=1, max_length=200)


async def _require_lineuser_id(authorization: Optional[str]) -> str:
    lineuser_id = await resolve_lineuser_id(authorization)
    if not lineuser_id:
        raise HTTPException(status_code=401, detail="ต้องเปิดหน้านี้จากในแอป LINE")
    return lineuser_id


@router.get("/userdata", response_class=HTMLResponse)
async def userdata_page():
    """Serve the profile LIFF page, injecting the LIFF id (empty = dev mode)."""
    html = _HTML_FILE.read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__LIFF_ID__", EDIT_PROFILE_ID or ""))


@router.get("/api/userdata/profile")
async def get_profile(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    lineuser_id = await _require_lineuser_id(authorization)
    return await user_service.get_profile(db, lineuser_id)


@router.put("/api/userdata/profile")
async def save_profile(
    profile: ProfileIn,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    lineuser_id = await _require_lineuser_id(authorization)
    await user_service.save_profile(db, lineuser_id, profile)
    return {"ok": True}
