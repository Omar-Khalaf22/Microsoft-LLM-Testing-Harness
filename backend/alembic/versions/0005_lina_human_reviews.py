"""Add append only human review history.

Revision ID: 0005_lina_reviews
Revises: 0004_prototype2
"""
import sqlalchemy as sa

from alembic import op

revision = "0005_lina_reviews"
down_revision = "0004_prototype2"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "human_reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "run_id", sa.Text(), sa.ForeignKey("test_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint("rating >= 0 AND rating <= 100", name="ck_human_review_rating"),
        sa.UniqueConstraint("run_id", "reviewer_id", "revision", name="uq_human_review_revision"),
    )
    op.create_index("ix_human_reviews_run_id", "human_reviews", ["run_id"])
    op.create_index("ix_human_reviews_reviewer_id", "human_reviews", ["reviewer_id"])

def downgrade():
    op.drop_index("ix_human_reviews_reviewer_id", table_name="human_reviews")
    op.drop_index("ix_human_reviews_run_id", table_name="human_reviews")
    op.drop_table("human_reviews")
