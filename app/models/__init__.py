from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from app.database import Base

class User(Base):
    __tablename__ = "users"
    lineuser_id = Column(String, primary_key=True, index=True)
    display_name = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class SurveySession(Base):
    __tablename__ = "survey_sessions"
    # ใช้ lineuser_id เป็น Primary Key ได้เลย เพราะ 1 คนควรมีแค่ 1 Session ที่กำลังทำอยู่
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"), primary_key=True)
    survey_version = Column(String, nullable=False)  # เช่น "v1"
    current_step = Column(Integer, default=0)        # ตอนนี้กำลังตอบคำถาม index ที่เท่าไหร่
    payload = Column(JSON, default=dict, nullable=False) 
    
    # เวลาเอาไว้เช็ค Timeout (ถ้าเกิน 1 ชม. ค่อยย้ายไปลงตาราง Incomplete)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class CompletedReport(Base):
    __tablename__ = "completed_reports"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"))
    survey_version = Column(String, nullable=False)
    # แยก Location ออกมาเป็น PostGIS Geometry เพื่อให้สถาปนิกเอาไปพล็อตแผนที่ได้ง่าย
    location_data = Column(Geometry('POINT', srid=4326), nullable=True)
    
    # ข้อมูลคำตอบทั่วไป (Text, Choice) จะถูกย้ายจาก Session มากองรวมกันในนี้
    payload = Column(JSON, nullable=False)
    
    
    # แยกลิงก์รูปภาพออกมาเก็บเป็นคอลัมน์ จะจัดการไฟล์ง่ายกว่ายัดลง JSON
    image_path = Column(String, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())

class IncompleteReport(Base):
    __tablename__ = "incomplete_reports"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"))
    survey_version = Column(String, nullable=False)
    location_data = Column(Geometry('POINT', srid=4326), nullable=True)
    
    # จุดที่คนเทงาน (เอาไว้วิเคราะห์ว่าคำถามข้อไหนคนหนีเยอะสุด)
    drop_off_step = Column(Integer, nullable=False)
    
    payload = Column(JSON, nullable=False)
    image_path = Column(String, nullable=True)
    
    status = Column(String, default="timeout") # สถานะ (เช่น timeout, cancelled)
    created_at = Column(DateTime, server_default=func.now())