"""Survey reports (V1 data). Kept for the dashboard's read-side — no new rows are
written under V2 (the survey chat engine is gone). Deleting these is a WAIT item
pending the dashboard team + the V2 dashboard contract (#81)."""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, text
from geoalchemy2 import Geometry

from app.database import Base
from app.models._common import get_bangkok_now


class CompletedReport(Base):
    __tablename__ = "completed_reports"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"))
    survey_version = Column(String, nullable=False)
    # แยก Location ออกมาเป็น PostGIS Geometry เพื่อให้สถาปนิกเอาไปพล็อตแผนที่ได้ง่าย
    location_data = Column(Geometry('POINT', srid=4326), nullable=True)

    # ข้อมูลคำตอบทั่วไป (Text, Choice) จะถูกย้ายจาก Session มากองรวมกันในนี้
    payload = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))


class IncompleteReport(Base):
    __tablename__ = "incomplete_reports"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"))
    survey_version = Column(String, nullable=False)
    location_data = Column(Geometry('POINT', srid=4326), nullable=True)

    # จุดที่คนเทงาน (เอาไว้วิเคราะห์ว่าคำถามข้อไหนคนหนีเยอะสุด)
    drop_off_route_id = Column(String, nullable=True)
    drop_off_step = Column(Integer, nullable=True)

    payload = Column(JSON, nullable=False)

    status = Column(String, default="timeout")  # สถานะ (เช่น timeout, cancelled)
    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))
