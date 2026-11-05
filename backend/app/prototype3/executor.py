"""Execute reserved records without creating IDs or inserting run records."""

from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol

from .judge import Judge, Provider
from .lina_points import earned_points, total_points
from .lina_rubric import RUBRICS
from .models import Criterion, Error, Outcome, Snapshot
from .storage import Storage


class Deterministic(Protocol):
    def validate(self, criterion: Criterion) -> None: ...

    def evaluate(self, snapshot: Snapshot, response: str, criterion: Criterion) -> Outcome: ...

    def earned_points(self, normalized: float, weight: float) -> float: ...

    def total_points(self, scores: list[float]) -> float: ...


class LinaAdapter:
    """Lazy imports: uses Lina's actual registry and aggregation when integrated."""

    def validate(self, criterion):
        from app.evaluation.registry import validate_criterion

        validate_criterion(criterion.criterion_id, criterion.parameters)

    def evaluate(self, snapshot, response, criterion):
        from app.evaluation.registry import evaluate_criterion

        _, normalized, detail = evaluate_criterion(
            criterion.criterion_id,
            response,
            criterion.parameters,
            {"prompt": snapshot.prompt, "approved_instructions": snapshot.instructions},
        )
        return Outcome(
            criterion_id=criterion.criterion_id,
            maximum_points=criterion.weight,
            status="completed",
            normalized_score=normalized,
            rationale=detail,
        )

    def earned_points(self, normalized, weight):
        return earned_points(normalized, weight)

    def total_points(self, scores):
        return total_points(scores)


class ReservedExecutor:
    def __init__(
        self, storage: Storage, provider: Provider, judge: Judge, deterministic: Deterministic
    ):
        self.storage, self.provider = storage, provider
        self.judge, self.deterministic = judge, deterministic

    def execute(self, run_id: str):
        # Validate before acquiring ownership or making any model calls.
        pending = self.storage.get(run_id)
        snapshot = Snapshot.model_validate(pending.snapshot.model_dump())
        for criterion in snapshot.criteria:
            evaluator = self.judge if criterion.criterion_id in RUBRICS else self.deterministic
            evaluator.validate(criterion)
        run = self.storage.claim(run_id).model_copy(deep=True)
        # Claim must return the same immutable configuration inspected above.
        if run.snapshot != snapshot:
            raise RuntimeError("Storage changed immutable reservation snapshot")
        run.started_at = datetime.now(UTC).isoformat()
        started = perf_counter()
        try:
            generated = self.provider.generate(
                snapshot.prompt,
                snapshot.model,
                snapshot.temperature,
                system_prompt=snapshot.instructions,
            )
            if generated.refused or generated.finish_reason != "stop":
                raise ValueError("Refused or incomplete generation")
            if not isinstance(generated.text, str) or len(generated.text) > 100000:
                raise ValueError("Invalid generated response")
            run.response, run.resolved_model, run.usage = (
                generated.text,
                generated.model,
                generated.usage,
            )
        except Exception:
            run.status, run.overall_status, run.evaluation_status = (
                "failed",
                "incomplete",
                "incomplete",
            )
            run.error = Error(code="provider_failure", message="Model generation failed.")
        else:
            # Storage failure must propagate; never report an unpersisted result as success.
            self.storage.checkpoint(run)
            for criterion in snapshot.criteria:
                evaluator = self.judge if criterion.criterion_id in RUBRICS else self.deterministic
                try:
                    outcome = evaluator.evaluate(snapshot, run.response, criterion)
                    if outcome.status == "completed":
                        value = outcome.normalized_score
                        if value is None or not 0 <= value <= 1:
                            raise ValueError("Invalid normalized score")
                        outcome.score = self.deterministic.earned_points(value, criterion.weight)
                except Exception:
                    outcome = Outcome(
                        criterion_id=criterion.criterion_id,
                        maximum_points=criterion.weight,
                        status="error",
                        error=Error(
                            code="evaluation_failure", message="Evaluator could not complete."
                        ),
                    )
                run.criteria.append(outcome)
            run.status = "completed"  # Generation succeeded, even if judgment failed.
            if any(x.status == "error" for x in run.criteria):
                run.evaluation_status, run.overall_status = "incomplete", "incomplete"
                run.error = Error(code="evaluation_incomplete", message="Total unavailable.")
            else:
                try:
                    run.score = self.deterministic.total_points([x.score for x in run.criteria])
                    run.evaluation_status = "completed"
                    values = {x.criterion_id: x.normalized_score for x in run.criteria}
                    run.failed_critical_criteria = [
                        p.criterion_id
                        for p in snapshot.critical_policy
                        if values[p.criterion_id] < p.threshold
                    ]
                    run.overall_status = "failed" if run.failed_critical_criteria else "passed"
                except Exception:
                    run.score = None
                    run.evaluation_status, run.overall_status = "incomplete", "incomplete"
                    run.error = Error(code="aggregation_failure", message="Total unavailable.")
        run.completed_at = datetime.now(UTC).isoformat()
        run.latency_ms = max(1, round((perf_counter() - started) * 1000))
        self.storage.finish(run)
        return run
