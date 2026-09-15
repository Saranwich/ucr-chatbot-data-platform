from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.report import Frequency, ProblemType, ReportStatus, Threat


class ReportLocation(BaseModel):
    id: UUID
    lat: float | None = None
    lon: float | None = None
    address: str | None = None


class ReportImage(BaseModel):
    id: UUID
    url: str
    desc: str | None = None


class ReportSummary(BaseModel):
    id: UUID
    created_at: datetime
    status: ReportStatus
    title: str | None = None
    type: ProblemType | None = None
    threat: Threat | None = None
    frequency: Frequency | None = None
    effect: str | None = None
    is_has_image: bool | None = None
    is_has_location: bool | None = None
    locations: list[ReportLocation] = Field(default_factory=list)
    images: list[ReportImage] = Field(default_factory=list)


class ReportDetail(ReportSummary):
    session_id: UUID


class ReportPage(BaseModel):
    items: list[ReportSummary]
    total: int


class UserSummary(BaseModel):
    id: UUID
    line_user_id: str
    name: str | None = None


class UserPage(BaseModel):
    items: list[UserSummary]
    total: int


class Total(BaseModel):
    total: int


class SessionTotal(Total):
    by_status: dict[str, int]


class ReportTotal(Total):
    by_type: dict[str, int]
    by_day: list["DailyReportTotal"]
    with_image: int
    with_location: int
    with_both: int
    without_media: int


class DailyReportTotal(BaseModel):
    date: date
    count: int


class Statistics(BaseModel):
    period_days: int
    users: Total
    sessions: SessionTotal
    reports: ReportTotal
    images: Total
    locations: Total
