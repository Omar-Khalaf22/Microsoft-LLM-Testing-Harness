"""Small reserved-ID adapter around the existing executor; no scheduler or new routes."""

from app.storage.executions import finalize_attempt, save_target_response


class ReservedResultRepository:
    def __init__(self, session_factory, access, run_id, lease_token):
        self.session_factory, self.access = session_factory, access
        self.run_id, self.lease_token = run_id, lease_token

    def checkpoint(self, generated, latency_ms):
        with self.session_factory.begin() as session:
            save_target_response(
                session,
                self.access,
                self.run_id,
                self.lease_token,
                content=generated.text,
                actual_model=generated.model if generated.model_reported else None,
                latency_ms=latency_ms,
                usage=generated.usage,
            )

    def save(self, result, **_):
        with self.session_factory.begin() as session:
            return finalize_attempt(session, self.access, self.run_id, self.lease_token, result)
