from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.run import TestRun


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "criterion_id", name="uq_evaluation_run_criterion"),
        CheckConstraint(
            "status IS NULL OR status IN ('completed','error')", name="ck_evaluation_status"
        ),
        CheckConstraint(
            (
                "earned_points IS NULL OR (earned_points >= 0 AND maximum_points "
                "IS NOT NULL AND earned_points <= maximum_points)"
            ),
            name="ck_evaluation_points",
        ),
        CheckConstraint(
            "maximum_points IS NULL OR (maximum_points >= 0 AND maximum_points <= 100)",
            name="ck_evaluation_maximum",
        ),
        CheckConstraint(
            "normalized_score IS NULL OR (normalized_score >= 0 AND normalized_score <= 1)",
            name="ck_evaluation_normalized",
        ),
        CheckConstraint(
            (
                "status IS NULL OR (status = 'completed' AND earned_points IS NOT"
                " NULL AND normalized_score IS NOT NULL) OR (status = 'error' AND"
                " earned_points IS NULL AND normalized_score IS NULL AND score IS"
                " NULL AND passed IS NULL)"
            ),
            name="ck_evaluation_completion",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 1",
            name="ck_evaluation_results_score_range",
        ),
    )
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    run_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    criterion_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    earned_points: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    maximum_points: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    normalized_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 10))
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    run: Mapped[TestRun] = relationship(back_populates="evaluations")
