"""Incremental P3 relational records, alongside the demonstrated P2 tables."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VersionCriterion(Base):
    __tablename__ = "version_criteria"
    __table_args__ = (CheckConstraint("maximum_points >= 0 AND maximum_points <= 100"),)
    test_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("test_versions.id"), primary_key=True
    )
    criterion_id: Mapped[str] = mapped_column(Text, primary_key=True)
    maximum_points: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Suite(Base):
    __tablename__ = "suites"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    creator_id: Mapped[str] = mapped_column(Text)


class SuiteRevision(Base):
    __tablename__ = "suite_revisions"
    __table_args__ = (CheckConstraint("revision > 0"),)
    suite_id: Mapped[str] = mapped_column(Text, ForeignKey("suites.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SuiteItem(Base):
    __tablename__ = "suite_items"
    __table_args__ = (CheckConstraint("position > 0"),)
    suite_id: Mapped[str] = mapped_column(Text, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("test_versions.id"), index=True
    )


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("project_id", "actor_id", "idempotency_key"),
        CheckConstraint("status IN ('pending','running','completed','failed')"),
    )
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    actor_id: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Preview(Base):
    __tablename__ = "previews"
    __table_args__ = (CheckConstraint("status IN ('completed','technical_error')"),)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, index=True)
    actor_id: Mapped[str] = mapped_column(Text)
    test_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("test_versions.id"), index=True
    )
    configuration_hash: Mapped[str] = mapped_column(Text)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    actual_model: Mapped[str | None] = mapped_column(Text)
    interpretation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_category: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
