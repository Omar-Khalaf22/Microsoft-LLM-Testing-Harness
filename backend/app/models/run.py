from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.model import Model
from app.models.test import TestVersion

if TYPE_CHECKING:
    from app.models.evaluation import EvaluationResult


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_test_runs_status",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_test_runs_latency_nonnegative",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_test_runs_input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_test_runs_output_tokens_nonnegative",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_test_runs_timestamp_order",
        ),
        Index(
            "ix_test_runs_status_started_at",
            "status",
            "started_at",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    test_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("test_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    input_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(BigInteger)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    test_version: Mapped[TestVersion] = relationship()
    model: Mapped[Model] = relationship()
    response: Mapped[ModelResponse | None] = relationship(
        back_populates="run",
        uselist=False,
        passive_deletes=True,
    )
    evaluations: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run",
        passive_deletes=True,
        order_by="EvaluationResult.id",
    )


class ModelResponse(Base):
    __tablename__ = "model_responses"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    run_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    run: Mapped[TestRun] = relationship(back_populates="response")
