from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, text

from app.database import Base
from app.models._common import get_bangkok_now


class ReportImage(Base):
    """รูปของ report ทุก source (DBML: report_images) — serve ผ่าน endpoint JWT (#81 images[])."""
    __tablename__ = "report_images"
    image_id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("reports.report_id"), nullable=False)
    image_key = Column(String, nullable=False)  # storage key (uploads/ → จุดเสียบ S3)
    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))

    __table_args__ = (Index("ix_report_images_report_id", "report_id"),)
