"""Shared model helpers."""
from datetime import datetime, timezone, timedelta


def get_bangkok_now():
    # naive Bangkok (UTC+7) — SQLAlchemy DateTime(timezone=False) ไม่รับ aware datetime บางกรณี
    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)
