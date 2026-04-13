from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from app.database import Base

class User(Base):
    __tablename__ = "users"
    lineuser_id = Column(String, primary_key=True, index=True)
    display_name = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class Question(Base):
    __tablename__ = "questions"
    question_id = Column(Integer, primary_key=True, autoincrement=True)
    question_text = Column(String, nullable=False)
    question_type = Column(String, nullable=False, default="text") 
    options = Column(JSON, nullable=True) 
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

class AskLog(Base):
    __tablename__ = "ask_logs"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"))
    question_id = Column(Integer, ForeignKey("questions.question_id"))
    asked_at = Column(DateTime, server_default=func.now())
    is_answered = Column(Boolean, default=False)

class Response(Base):
    __tablename__ = "responses"
    response_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"))
    question_id = Column(Integer, ForeignKey("questions.question_id"))
    response_type = Column(String, nullable=False) 
    response_text = Column(Text, nullable=True)
    
    # NEW: Using PostGIS Geometry type for professional mapping
    # 'POINT' means a single GPS coordinate
    # 'srid=4326' is the global standard (WGS84) used by GPS and Google Maps
    location_data = Column(Geometry('POINT', srid=4326), nullable=True)
    
    image_path = Column(String, nullable=True)
    response_time = Column(DateTime, server_default=func.now())
