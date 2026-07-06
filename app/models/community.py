from sqlalchemy import Column, String, Integer, Float, Boolean, text

from app.database import Base


class Community(Base):
    """ชุมชน — single source of truth ของชื่อชุมชน (DBML: communities).

    dropdown หน้า profile / forecast ทีม data / users.community_id → อ้างตารางนี้
    (เลิก hardcode ชื่อใน HTML = จบปัญหาสะกดไม่ตรงกัน 3 ที่). seed จาก
    services/lookups.COMMUNITIES ตอน migrate.
    """
    __tablename__ = "communities"
    community_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)  # ชื่อ canonical
    lat = Column(Float, nullable=True)   # พิกัดกลางชุมชน — จับคู่กับ forecast
    lon = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
