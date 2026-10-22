"""Add explicit criterion evidence and generated recommendation snapshots, preserving legacy rows.

Revision ID: 0004_prototype2
Revises: 0003_version_names
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_prototype2"
down_revision = "0003_version_names"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "criteria_recommendations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for name, kind in [
        ("criterion_id", sa.Text()),
        ("status", sa.Text()),
        ("earned_points", sa.Numeric(5, 2)),
        ("maximum_points", sa.Numeric(5, 2)),
        ("normalized_score", sa.Numeric(12, 10)),
    ]:
        op.add_column("evaluation_results", sa.Column(name, kind, nullable=True))
    op.alter_column("evaluation_results", "passed", nullable=True)
    op.alter_column("evaluation_results", "score", nullable=True)
    op.create_unique_constraint(
        "uq_evaluation_run_criterion", "evaluation_results", ["run_id", "criterion_id"]
    )
    op.create_check_constraint(
        "ck_evaluation_status",
        "evaluation_results",
        "status IS NULL OR status IN ('completed','error')",
    )
    op.create_check_constraint(
        "ck_evaluation_points",
        "evaluation_results",
        (
            "earned_points IS NULL OR (earned_points >= 0 AND maximum_points "
            "IS NOT NULL AND earned_points <= maximum_points)"
        ),
    )
    op.create_check_constraint(
        "ck_evaluation_maximum",
        "evaluation_results",
        "maximum_points IS NULL OR (maximum_points >= 0 AND maximum_points <= 100)",
    )
    op.create_check_constraint(
        "ck_evaluation_normalized",
        "evaluation_results",
        "normalized_score IS NULL OR (normalized_score >= 0 AND normalized_score <= 1)",
    )
    op.create_check_constraint(
        "ck_evaluation_completion",
        "evaluation_results",
        (
            "status IS NULL OR (status = 'completed' AND earned_points IS NOT"
            " NULL AND normalized_score IS NOT NULL) OR (status = 'error' AND"
            " earned_points IS NULL AND normalized_score IS NULL AND score IS"
            " NULL AND passed IS NULL)"
        ),
    )


def downgrade():
    # Refuse destructive downgrade when incomplete evidence cannot fit the old non-null fields.
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT count(*) FROM evaluation_results WHERE passed IS NULL OR score IS NULL")
    ):
        raise RuntimeError(
            "Cannot downgrade while incomplete evaluation evidence exists. Ex"
            "port and review it first."
        )
    for name in [
        "ck_evaluation_completion",
        "ck_evaluation_normalized",
        "ck_evaluation_maximum",
        "ck_evaluation_points",
        "ck_evaluation_status",
    ]:
        op.drop_constraint(name, "evaluation_results", type_="check")
    op.drop_constraint("uq_evaluation_run_criterion", "evaluation_results", type_="unique")
    for name in ["normalized_score", "maximum_points", "earned_points", "status", "criterion_id"]:
        op.drop_column("evaluation_results", name)
    op.alter_column("evaluation_results", "passed", nullable=False)
    op.alter_column("evaluation_results", "score", nullable=False)
    op.drop_table("criteria_recommendations")
