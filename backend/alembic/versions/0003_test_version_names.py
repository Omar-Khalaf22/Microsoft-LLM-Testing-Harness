"""Give each test version its own display name.

Revision ID: 0003_version_names
Revises: 0002_week5
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_version_names"
down_revision: str | None = "0002_week5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("test_versions", sa.Column("name", sa.Text(), nullable=True))
    op.execute(
        "UPDATE test_versions AS version SET name = test.name "
        "FROM tests AS test WHERE version.test_id = test.id"
    )
    op.alter_column("test_versions", "name", nullable=False)


def downgrade() -> None:
    op.drop_column("test_versions", "name")
