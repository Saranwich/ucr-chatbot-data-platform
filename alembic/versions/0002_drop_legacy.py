"""drop the 4 legacy tables (V1 survey + pre-cutover form/broadcast)

After M4: the survey data is backfilled into `reports` (app/scripts/backfill_surveys)
and every live channel writes only `reports`, so completed_reports / incomplete_reports
/ form_reports / broadcast_reports have no readers or writers left. This drops them.

# ponytail: upgrade uses DROP TABLE IF EXISTS (not op.drop_table). 0001 builds the
# schema via Base.metadata.create_all off the live models; M4 deletes the legacy
# models, so on a *fresh* DB 0001 no longer creates these 4 tables and a plain
# op.drop_table would fail. IF EXISTS makes 0002 a no-op on fresh DBs and the real
# drop on deployments still carrying them.
# ponytail: downgrade needs `import geoalchemy2` so the Geometry columns render in the
# explicit create_table DDL (the legacy models are gone — can't lean on them here).

Revision ID: 0002_drop_legacy
Revises: 0001_v2_reports_schema
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2

# revision identifiers, used by Alembic.
revision = "0002_drop_legacy"
down_revision = "0001_v2_reports_schema"
branch_labels = None
depends_on = None

_LEGACY_TABLES = ("completed_reports", "incomplete_reports", "form_reports", "broadcast_reports")

_CREATED_AT_DEFAULT = sa.text("(now() at time zone 'utc' at time zone 'asia/bangkok')")


def upgrade() -> None:
    for table in _LEGACY_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    # Explicit re-create DDL — reversible without the (now-deleted) legacy models.
    op.create_table(
        "completed_reports",
        sa.Column("report_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("lineuser_id", sa.String, sa.ForeignKey("users.lineuser_id")),
        sa.Column("survey_version", sa.String, nullable=False),
        sa.Column("location_data", geoalchemy2.Geometry("POINT", srid=4326), nullable=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=_CREATED_AT_DEFAULT),
    )
    op.create_table(
        "incomplete_reports",
        sa.Column("report_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("lineuser_id", sa.String, sa.ForeignKey("users.lineuser_id")),
        sa.Column("survey_version", sa.String, nullable=False),
        sa.Column("location_data", geoalchemy2.Geometry("POINT", srid=4326), nullable=True),
        sa.Column("drop_off_route_id", sa.String, nullable=True),
        sa.Column("drop_off_step", sa.Integer, nullable=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String, server_default="timeout"),
        sa.Column("created_at", sa.DateTime, server_default=_CREATED_AT_DEFAULT),
    )
    op.create_table(
        "form_reports",
        sa.Column("report_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("lineuser_id", sa.String, sa.ForeignKey("users.lineuser_id"), nullable=True),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("description", sa.String, nullable=False),
        sa.Column("location_data", geoalchemy2.Geometry("POINT", srid=4326), nullable=True),
        sa.Column("image_path", sa.String, nullable=True),
        sa.Column("status", sa.String, server_default="new"),
        sa.Column("created_at", sa.DateTime, server_default=_CREATED_AT_DEFAULT),
    )
    op.create_table(
        "broadcast_reports",
        sa.Column("report_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("lineuser_id", sa.String, sa.ForeignKey("users.lineuser_id"), nullable=True),
        sa.Column("alert_type", sa.String, nullable=False),
        sa.Column("confirmed", sa.Integer, server_default="0", nullable=False),
        sa.Column("location_data", geoalchemy2.Geometry("POINT", srid=4326), nullable=True),
        sa.Column("image_path", sa.String, nullable=True),
        sa.Column("community", sa.String, nullable=True),
        sa.Column("status", sa.String, server_default="done", nullable=False),
        sa.Column("note", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=_CREATED_AT_DEFAULT),
    )
