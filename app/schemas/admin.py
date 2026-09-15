from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.report import Frequency, ProblemType, ReportStatus, Threat


class AdminLocation(BaseModel):
    id: UUID
    lat: float | None = None
    lon: float | None = None
    address: str | None = None


class AdminImage(BaseModel):
    id: UUID
    url: str
    desc: str | None = None


class AdminReportSummary(BaseModel):
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
    locations: list[AdminLocation] = Field(default_factory=list)
    images: list[AdminImage] = Field(default_factory=list)


class AdminReportDetail(AdminReportSummary):
    session_id: UUID


class AdminReportPage(BaseModel):
    items: list[AdminReportSummary]
    total: int


class AdminUser(BaseModel):
    id: UUID
    line_user_id: str
    name: str | None = None


class AdminUserPage(BaseModel):
    items: list[AdminUser]
    total: int


class TotalStatistic(BaseModel):
    total: int


class GroupedStatistic(TotalStatistic):
    by_status: dict[str, int]


class ReportStatistic(TotalStatistic):
    by_type: dict[str, int]
    by_day: list["DailyReportStatistic"]
    with_image: int
    with_location: int
    with_both: int
    without_media: int


class DailyReportStatistic(BaseModel):
    date: date
    count: int


class AdminStatistics(BaseModel):
    period_days: int
    users: TotalStatistic
    sessions: GroupedStatistic
    reports: ReportStatistic
    images: TotalStatistic
    locations: TotalStatistic
