"""v2 full schema — every table + GiST + seed (Alembic is the sole schema owner)

Greenfield DBML v2 (docs/db_redesign_v2.dbml). Produces the COMPLETE schema on an
empty DB in one `alembic upgrade head`: users + the 4 legacy tables + the 6 v2
tables (communities, categories, conversations, reports, report_images, outreach),
users.community_id FK, the GiST index on reports.location_data, and the seeded
communities/categories from services/lookups.

# ponytail: this migration delegates ALL table DDL to Base.metadata.create_all
# (the models are the single source of column truth) and owns only the GiST index
# + the master-data seed. Trade-off: structural changes ride model edits, not
# hand-written op.create_table — fine while 0001 is the greenfield baseline; the
# first real ALTER migration writes explicit ops against this as the base.
# ponytail: no CHECK constraints on source/severity/status — DBML lists them. The
# severity enum is now low/medium/high on both sides (tool spec reconciled to DBML);
# enforced app-side (tool spec) + by FK (category_id). A CHECK migration can layer on
# top of this baseline now that the drift is gone.

Revision ID: 0001_v2_reports_schema
Revises:
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2  # noqa: F401 — so Geometry columns render in this migration

from app.database import Base
import app.models  # noqa: F401 — registers every table on Base.metadata
from app.services.lookups import CATEGORIES, COMMUNITIES

# revision identifiers, used by Alembic.
revision = "0001_v2_reports_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Geometry columns need PostGIS — make the migration self-contained (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # All table DDL (users + 4 legacy + 6 v2). Models set reports.location_data
    # spatial_index=False, so create_all does NOT emit the GiST — we own it below.
    Base.metadata.create_all(bind=bind)
    # GiST on the geometry — dashboard map queries (ST_X/ST_Y, spatial filters).
    op.create_index("idx_reports_geom", "reports", ["location_data"], postgresql_using="gist")
    # Seed master data (single source: services/lookups).
    op.bulk_insert(
        sa.table("communities", sa.column("name", sa.String)),
        [{"name": name} for name in COMMUNITIES],
    )
    op.bulk_insert(
        sa.table("categories", sa.column("value", sa.String)),
        [{"value": value} for value in CATEGORIES],
    )


def downgrade() -> None:
    # Dropping each table cascades its indexes (incl. idx_reports_geom); drop_all
    # resolves FK ordering. Greenfield teardown — 0001 is the base revision.
    Base.metadata.drop_all(bind=op.get_bind())
