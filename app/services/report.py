"""Report persistence (V2) — fake CSV store for now.

# ponytail: CSV stand-in so the full chat → extract → save flow runs end to end.
# Columns mirror the full v2 `reports` schema (docs/db_redesign_v2.dbml), so the
# swap to a Postgres insert (session from database_manager) in M3 is mechanical.
# The record() hook in ai_tool fills source/status/is_complete; missing fields = "".
"""
import csv
import os
from datetime import datetime, timedelta, timezone

_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "reports.csv")
# คอลัมน์ตามตาราง reports (created_at + lineuser_id คุมโดย save(); tool ให้ location → location_text)
_FIELDS = [
    "created_at", "lineuser_id", "community_id", "source", "source_ref",
    "category", "notes", "severity", "title", "status", "is_complete",
    "location_text", "extraction_confidence", "confidence_by_field", "payload",
]


def save(lineuser_id: str, report: dict) -> None:
    """Append one report as a CSV row (writes a header on first use)."""
    row = {f: report.get(f, "") for f in _FIELDS}
    row["created_at"] = datetime.now(timezone(timedelta(hours=7))).isoformat()
    row["lineuser_id"] = lineuser_id
    row["location_text"] = report.get("location", "")  # tool arg 'location' → คอลัมน์ location_text
    new_file = not os.path.exists(_CSV_PATH)
    with open(_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
