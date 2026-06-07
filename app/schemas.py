from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

class DashboardStats(BaseModel):
    total_users: int
    total_completed_reports: int
    total_incomplete_reports: int

class ReportLocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ReportImage(BaseModel):
    question_id: str          # คำถามที่รูปนี้มาจาก (เช่น q_photo, q_flood_photo)
    image_id: str             # LINE message content id
    image_url: str            # proxy URL ที่ดึงรูปได้ (/api/dashboard/image/{id})

class CompletedReportSchema(BaseModel):
    report_id: int
    lineuser_id: str
    survey_version: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    payload: Any
    images: List[ReportImage] = []   # ดึงออกมาจาก payload — รองรับ 0, 1, หรือหลายรูป
    created_at: datetime

    class Config:
        from_attributes = True
