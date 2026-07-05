from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, text
from geoalchemy2 import Geometry

from app.database import Base
from app.models._common import get_bangkok_now


class FormReport(Base):
    """แจ้งปัญหา (problem report submitted via the LIFF report form).

    Separate domain from survey reports (ADR 0004): no survey_version / route /
    payload — just one free-standing report. Geospatial + image columns mirror
    CompletedReport so the dashboard map can plot it the same way.
    lineuser_id is nullable: real identity arrives via LIFF access-token verify,
    but the form degrades to anonymous (null) when opened outside LINE (dev).
    """
    __tablename__ = "form_reports"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    lineuser_id = Column(String, ForeignKey("users.lineuser_id"), nullable=True)
    category = Column(String, nullable=True)
    description = Column(String, nullable=False)
    location_data = Column(Geometry('POINT', srid=4326), nullable=True)
    image_path = Column(String, nullable=True)   # filename under uploads/ (ADR 0005 → S3 later)
    status = Column(String, default="new")
    created_at = Column(DateTime, default=get_bangkok_now, server_default=text("(now() at time zone 'utc' at time zone 'asia/bangkok')"))
