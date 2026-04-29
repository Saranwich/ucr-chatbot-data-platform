from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

class DashboardStats(BaseModel):
    total_users: int
    total_completed_reports: int
    total_incomplete_reports: int

class ReportLocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class CompletedReportSchema(BaseModel):
    report_id: int
    lineuser_id: str
    survey_version: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    payload: Any
    image_path: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
