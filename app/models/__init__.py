from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, text
from sqlalchemy.sql import func
from datetime import datetime, timezone, timedelta

# ฟังก์ชันช่วยดึงเวลาปัจจุบันแบบ Bangkok (UTC+7) สำหรับ Python-side default
# เราต้องใช้ .replace(tzinfo=None) เพื่อให้เป็น naive datetime (ไม่มี timezone แปะไป) 
# เพราะ SQLAlchemy Column DateTime(timezone=False) ไม่รองรับ aware datetime ในบางกรณี
def get_bangkok_now():
    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)
from geoalchemy2 import Geometry
from app.database import Base

class User(Base):
    __tablename__ = "users"
    lineuser_id = Column(String, primary_key=True, index=True)
    display_name = Column(String)
    has_completed_profile = Column(Integer, default=0, nullable=False)  # 0=false, 1=true
    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))

class SurveySession(Base):
    __tablename__ = "survey_sessions"
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"), primary_key=True)
    survey_version = Column(String, nullable=False)
    current_route_id = Column(String, nullable=True)   # which route the user is in
    current_step = Column(Integer, default=0)          # step index within current_route_id
    route_history = Column(JSON, default=list, nullable=False)  # stack: [{"route_id": str, "step": int}]
    payload = Column(JSON, default=dict, nullable=False)
    pending_multi_select = Column(JSON, default=dict, nullable=False)  # {question_id: [answers]}
    updated_at = Column(DateTime, default=get_bangkok_now, onupdate=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))

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

    status = Column(String, default="timeout") # สถานะ (เช่น timeout, cancelled)
    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))