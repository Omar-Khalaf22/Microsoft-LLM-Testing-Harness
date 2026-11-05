"""Append only human assessments, independent of automatic evaluations."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class HumanReview(Base):
    __tablename__ = "human_reviews"
    __table_args__ = (
        CheckConstraint("rating >= 0 AND rating <= 100", name="ck_human_review_rating"),
        UniqueConstraint("run_id", "reviewer_id", "revision", name="uq_human_review_revision"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    attribution: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
