from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, text

from app.database import Base
from app.models._common import get_bangkok_now


class Conversation(Base):
    """anchor เบาๆ ของบทสนทนา AI (DBML: conversations) — ไม่มีเนื้อบทสนทนาในนี้!

    1 บทสนทนา = 1 แถวเล็ก ไว้ query insight (กี่ turn / เทกลางทางกี่ %). เนื้อจริง:
    live → Redis (TTL) / จบแล้ว dump → storage seam ตาม archive_key.
    """
    __tablename__ = "conversations"
    conversation_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"), nullable=False)
    trigger = Column(String, nullable=False)   # 'broadcast:flood' | 'user_initiated' | ...
    status = Column(String, nullable=False)    # 'active' | 'done' | 'abandoned'
    archive_key = Column(String, nullable=True)  # storage key ของบทสนทนาเต็มที่ dump เก็บ
    started_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))
    ended_at = Column(DateTime, nullable=True)

    # หา conversation ที่ active ของ user (routing ข้อความเข้า AI)
    __table_args__ = (Index("ix_conversations_lineuser_status", "lineuser_id", "status"),)
