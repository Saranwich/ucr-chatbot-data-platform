from sqlalchemy import Column, String, Integer, DateTime, text

from app.database import Base
from app.models._common import get_bangkok_now


class User(Base):
    __tablename__ = "users"
    lineuser_id = Column(String, primary_key=True, index=True)
    display_name = Column(String)
    has_completed_profile = Column(Integer, default=0, nullable=False)  # 0=false, 1=true
    # Profile — canonical store, กรอก/แก้ไขผ่าน Userdata LIFF ทางเดียว (ไม่ถามใน survey แล้ว)
    nickname = Column(String)
    age_range = Column(String)
    gender = Column(String)
    community = Column(String)
    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))
