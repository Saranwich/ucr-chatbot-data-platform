"""Report persistence (V2) — fake CSV store for now.

# ponytail: CSV stand-in so the full chat → extract → save flow runs end to end.
# Swap save() for a Postgres insert (session from database_manager) once Pim's
# report schema lands. Columns already match §6.5: category + notes required,
# location + severity optional.
"""
import csv
import os
from datetime import datetime, timedelta, timezone

_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "reports.csv")
_FIELDS = ["created_at", "lineuser_id", "category", "notes", "location", "severity"]


def save(lineuser_id: str, report: dict) -> None:
    """Append one completed report as a CSV row (writes a header on first use)."""
    row = {
        "created_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "lineuser_id": lineuser_id,
        "category": report.get("category", ""),
        "notes": report.get("notes", ""),
        "location": report.get("location", ""),
        "severity": report.get("severity", ""),
    }
    new_file = not os.path.exists(_CSV_PATH)
    with open(_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
