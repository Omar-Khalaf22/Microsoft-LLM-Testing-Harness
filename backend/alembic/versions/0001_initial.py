"""Create the initial empty schema baseline.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-09
"""

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """No domain tables are needed during Phase 0."""


def downgrade() -> None:
    """The empty baseline has nothing to remove."""
