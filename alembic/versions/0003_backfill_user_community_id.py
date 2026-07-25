"""backfill users.community_id from the legacy users.community varchar

save_profile (app/services/user.py) previously wrote only the varchar
community column and never set community_id (FK) — see issue #115. This is
a one-shot backfill for rows created before that fix: exact-match users.community
against communities.name and fill community_id where it's still null. Rows whose
varchar text never matched a communities.name stay null (dropdown drift,
same as the app-side unmatched case going forward).

Revision ID: 0003_backfill_user_community_id
Revises: 0002_drop_legacy
Create Date: 2026-07-25
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_backfill_user_community_id"
down_revision = "0002_drop_legacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET community_id = c.community_id
        FROM communities c
        WHERE users.community = c.name AND users.community_id IS NULL
        """
    )


def downgrade() -> None:
    # Not reversible — can't distinguish rows this backfill set from rows
    # that already had community_id populated another way.
    pass
