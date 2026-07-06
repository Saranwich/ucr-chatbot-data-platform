from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, text

from app.database import Base
from app.models._common import get_bangkok_now


class Outreach(Base):
    """log การยิงแจ้งเตือน (DBML: outreach) — 1 push = 1 แถวเล็ก.

    รองรับกันสแปม: frequency cap (เช็ค max(sent_at) ก่อนยิง) + response rate ต่อชุมชน.
    """
    __tablename__ = "outreach"
    outreach_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"), nullable=False)
    community_id = Column(Integer, ForeignKey("communities.community_id"), nullable=True)
    alert_type = Column(String, nullable=False)   # 'flood' | 'heat' | 'both'
    sent_at = Column(DateTime, nullable=False, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))
    response = Column(String, nullable=True)       # null=เมิน | 'confirmed' | 'declined'
    conversation_id = Column(Integer, ForeignKey("conversations.conversation_id"), nullable=True)  # ถ้าตอบแล้วกลายเป็นบทสนทนา

    # ★ frequency cap: ยิงหาคนนี้ล่าสุดเมื่อไหร่
    __table_args__ = (Index("ix_outreach_lineuser_sent", "lineuser_id", "sent_at"),)
