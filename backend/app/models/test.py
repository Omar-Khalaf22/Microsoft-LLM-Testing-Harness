from __future__ import annotations

from datetime import datetime
from typing import Any

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Test(Base):
    __tablename__ = "tests"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    versions: Mapped[list[TestVersion]] = relationship(
        back_populates="test",
        passive_deletes=True,
    )


class TestVersion(Base):
    __tablename__ = "test_versions"
    __table_args__ = (
        UniqueConstraint(
            "test_id",
            "version",
            name="uq_test_versions_test_id_version",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_test_versions_version_positive",
        ),
    )
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    test_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_definition: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    test: Mapped[Test] = relationship(back_populates="versions")
