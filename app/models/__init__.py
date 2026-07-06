"""SQLAlchemy models — split per file, re-exported so `from app.models import X` works.

All models bind to the single Base (app.database), so importing this package
registers every table for Base.metadata.create_all.
"""
from app.models._common import get_bangkok_now
from app.models.user import User
# V2 greenfield schema (DBML v2) — Alembic-owned tables. The 4 legacy tables
# (completed/incomplete/form/broadcast reports) were dropped in Alembic 0002 (M4).
from app.models.community import Community
from app.models.category import Category
from app.models.conversation import Conversation
from app.models.reports import Report
from app.models.report_image import ReportImage
from app.models.outreach import Outreach

__all__ = [
    "get_bangkok_now",
    "User",
    "Community",
    "Category",
    "Conversation",
    "Report",
    "ReportImage",
    "Outreach",
]
