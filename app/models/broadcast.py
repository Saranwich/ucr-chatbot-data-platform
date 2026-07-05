from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, text
from geoalchemy2 import Geometry

from app.database import Base
from app.models._common import get_bangkok_now


class BroadcastReport(Base):
    """รายงานสภาพอากาศจาก broadcast แจ้งเตือน (flood / heat / both).

    Flow: บอทยิง broadcast ถามยืนยัน → user ตอบ + (ถ้าเจอ) แชร์ location + รูป → เก็บที่นี่
    Standalone แบบ FormReport — geo + image column ตรงกับ CompletedReport/FormReport
    ให้ dashboard พล็อตหมุดได้เหมือนกัน. lineuser_id nullable กันเคสยังไม่มี profile.

    alert_type เก็บเป็น code ("flood"/"heat"/"both") — map เป็นชื่อหมวดไทยตอน serve
    ให้ dashboard (ดู BROADCAST_CATEGORY ใน services/dashboard.py). "both" ถูกแตกเป็น
    2 หมุด (flood + heat) ตอน serve.
    """
    __tablename__ = "broadcast_reports"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"), nullable=True)
    alert_type = Column(String, nullable=False)            # "flood" | "heat" | "both"
    confirmed = Column(Integer, default=0, nullable=False)  # 0=ไม่เจอ, 1=เจอ (สไตล์เดียวกับ has_completed_profile)
    location_data = Column(Geometry('POINT', srid=4326), nullable=True)  # จุดน้ำท่วม (flood/both); heat มักเป็น null
    image_path = Column(String, nullable=True)             # storage key ของรูปจุดน้ำขัง
    community = Column(String, nullable=True)              # snapshot ชุมชนตอนรายงาน
    # state ของ flow เก็บข้อมูล — บอทดูตรงนี้เพื่อรู้ว่า user คนนี้อยู่ขั้นไหน
    # awaiting_note → awaiting_location → awaiting_photo → done  (ดู broadcast_flow_handler)
    status = Column(String, default="done", nullable=False)
    note = Column(String, nullable=True)                   # ข้อความที่ user เล่า/บ่น (free text)
    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))
