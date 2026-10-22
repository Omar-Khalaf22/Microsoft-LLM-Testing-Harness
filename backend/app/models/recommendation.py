"""Generated criteria remain separate from the configuration approved for a run."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CriteriaRecommendation(Base):
    __tablename__ = "criteria_recommendations"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
