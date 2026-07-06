"""Manual broadcast trigger — POST /api/broadcast/run (JWT, แอดมินกดยิงเอง).

โหมดกดเอง = ส่งทันทีไม่สนเวลาใน forecast; ตัว logic ทั้งหมดอยู่ใน weather.run_broadcast
(ตัวเดียวกับที่ scheduler เรียก) — route นี้แค่รับ param แล้วส่งต่อ
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.weather import run_broadcast
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/broadcast", tags=["broadcast"])


class RunBroadcastIn(BaseModel):
    date: str | None = None   # "YYYY-MM-DD" — ไม่ใส่ = วันนี้ (คันโยกเดโม่: เลือกวันที่มี alert)
    force: bool = False       # ข้าม cap 7 วัน (คนค้าง flow เก่ายังโดนข้ามเสมอ)


@router.post("/run")
async def run(body: RunBroadcastIn, current_user: dict = Depends(get_current_user)):
    return await run_broadcast(date=body.date, force=body.force)
