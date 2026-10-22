from sqlalchemy.orm import Session, sessionmaker

from app.models.recommendation import CriteriaRecommendation


class RecommendationRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def save(self, snapshot: dict) -> None:
        with self.session_factory.begin() as session:
            session.add(CriteriaRecommendation(id=snapshot["recommendation_id"], snapshot=snapshot))

    def get(self, recommendation_id: str) -> dict | None:
        with self.session_factory() as session:
            row = session.get(CriteriaRecommendation, recommendation_id)
            return row.snapshot if row else None
