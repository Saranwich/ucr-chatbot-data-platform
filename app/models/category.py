from sqlalchemy import Column, String, Integer, Boolean, text

from app.database import Base


class Category(Base):
    """enum หมวดปัญหาแบบตาราง lookup (DBML: categories) — เพิ่มค่า = INSERT ไม่ต้อง migrate.

    ล็อก enum 2 ชั้น: tool spec record_complaint (AI เลือกได้เฉพาะค่าในลิสต์) +
    FK reports.category_id. seed จาก services/lookups.CATEGORIES ตอน migrate.
    """
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    value = Column(String, unique=True, nullable=False)  # ชื่อหมวด เช่น "ขยะ", "น้ำท่วม/น้ำขัง"
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)  # ปิดใช้โดยไม่ลบ — แถวเก่ายังอ้างได้
