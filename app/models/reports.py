"""ตารางกลาง reports (DBML v2) — ผลกลั่นจากทุกช่องทาง (ai/broadcast/form_report/survey).

หมายเหตุชื่อไฟล์: reports.py (พหูพจน์) — เดิมเลี่ยงชนกับ legacy report.py ซึ่งถูกลบไปแล้ว
ใน M4. dashboard V2 อ่านตารางนี้ที่เดียว (#81).
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry

from app.database import Base
from app.models._common import get_bangkok_now


class Report(Base):
    __tablename__ = "reports"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.conversation_id"), nullable=True)  # null สำหรับ form
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"), nullable=True)  # null ได้ (form anonymous)
    community_id = Column(Integer, ForeignKey("communities.community_id"), nullable=True)  # snapshot ชุมชน

    source = Column(String, nullable=False)      # 'ai' | 'broadcast' | 'form_report' | 'survey'
    source_ref = Column(String, nullable=True)   # บริบท เช่น broadcast alert / survey_version

    # 4 field ของ record_complaint (ชื่อตามภาษา domain: category/notes)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)  # จาก tool enum + FK
    notes = Column(String, nullable=True)        # รายละเอียดในคำพูดของ resident
    severity = Column(String, nullable=True)     # 'low' | 'medium' | 'high' (ล็อก enum ที่ tool spec)
    title = Column(String, nullable=True)        # AI สรุปสั้น 1 บรรทัด (#81 problem_summary)

    status = Column(String, nullable=False)      # 'completed' | 'new' | 'abandoned' | 'timeout' | 'cancelled'
    is_complete = Column(Boolean, nullable=False)  # ตั้งใจไม่มี default — ผู้เขียนทุกตัวต้องใส่เอง

    location_text = Column(String, nullable=True)  # ตำแหน่งแบบคำพูด เช่น "หน้าปากซอย 5"
    # ponytail: spatial_index=False — Alembic migration เป็นเจ้าของ GiST index (schema authority)
    location_data = Column(Geometry('POINT', srid=4326, spatial_index=False), nullable=True)

    extraction_confidence = Column(Float, nullable=True)  # คุณภาพการสกัดของ AI (#81)
    confidence_by_field = Column(JSONB, nullable=True)     # confidence รายช่อง — metadata
    payload = Column(JSONB, nullable=True)                 # raw extraction 1 ก้อน/report (#81)

    created_at = Column(DateTime, nullable=False, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))
