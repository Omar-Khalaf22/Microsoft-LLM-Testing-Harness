"""Negative database checks and import validation beyond the successful workflow."""

from decimal import Decimal

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from test_p3_storage import definition, execute, profile, reserve, setup

from app.database import SessionLocal
from app.evaluation.providers import ProviderResponse
from app.evaluation.rubric_integration import evaluate_rubric
from app.models import EvaluationResult
from app.models import TestVersion as Version
from app.storage.definitions import create_test, create_test_version
from app.storage.errors import Conflict
from app.storage.executions import claim_attempt, reserve_attempts
from app.storage.records import SavedDefinition
from app.storage.transfer import EvidenceBundle, export_evidence


def test_draft_approval_creates_immutable_new_version(access):
    from app.storage.records import TestReference

    with SessionLocal.begin() as s:
        draft = create_test(s, access, definition().model_copy(update={"state": "draft"}))
        ref = TestReference(test_id=draft.test_id, test_version=1)
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            reserve_attempts(s, access, [profile()], test=ref)
    with SessionLocal.begin() as s:
        approved = create_test_version(s, access, ref.test_id, definition(), expected_version=1)
        assert approved.version == 2
    with SessionLocal() as s:
        assert (
            s.scalar(
                select(Version).where(Version.test_id == ref.test_id, Version.version == 1)
            ).approval["state"]
            == "draft"
        )


@pytest.mark.parametrize("criterion", ["factual_accuracy", "evidence_grounding", "completeness"])
def test_missing_prerequisites_and_planned_criterion_are_rejected(criterion):
    with pytest.raises(ValueError):
        SavedDefinition(
            name="Unsupported",
            prompt="Question",
            criteria=[{"criterion_id": criterion, "parameters": {}, "weight": 100}],
        )


def test_database_rejects_wrong_membership_and_maximum(access):
    run_id = reserve(access, setup(access))["attempts"][0]["run_id"]
    with SessionLocal.begin() as s:
        claim_attempt(s, access, run_id)
    from app.models import TestRun

    with SessionLocal() as s:
        vid = s.get(TestRun, run_id).test_version_id
    for criterion, maximum in [("unknown", 100), ("valid_json", 99)]:
        with SessionLocal.begin() as s:
            with pytest.raises(IntegrityError):
                s.execute(
                    insert(EvaluationResult).values(
                        run_id=run_id,
                        test_version_id=vid,
                        criterion_id=criterion,
                        maximum_points=maximum,
                        method=criterion,
                        passed=True,
                        score=Decimal("0.5"),
                        status="completed",
                        earned_points=50,
                        normalized_score=Decimal("0.5"),
                        details={},
                    )
                )


def test_import_rejects_snapshot_tampering_duplicates_and_nonfinite(access):
    run_id = reserve(access, setup(access))["attempts"][0]["run_id"]
    execute(access, run_id)
    with SessionLocal() as s:
        bundle = export_evidence(s, access, [run_id])
    for mutate in (
        lambda b: b["runs"].append(b["runs"][0]),
        lambda b: b["runs"][0]["configuration"]["result_snapshot"].update(score=99),
        lambda b: b["runs"][0]["configuration"]["result_snapshot"]["criteria"][0].update(score=99),
        lambda b: b["runs"][0]["configuration"]["snapshot"]["profile"].update(profile_revision=99),
        lambda b: b["runs"][0]["configuration"].update(api_key="do-not-store"),
        lambda b: b["runs"][0].update(latency_ms=float("inf")),
    ):
        data = bundle.model_dump(mode="json")
        mutate(data)
        with pytest.raises(ValueError):
            EvidenceBundle.model_validate(data)


def test_judge_alias_and_reported_identity_remain_distinct():
    import json

    class Judge:
        def generate(self, prompt, model, *args, **kwargs):
            payload = json.loads(prompt)
            assert payload["response"] == "4"
            return ProviderResponse(
                json.dumps(
                    {
                        "score": 1,
                        "rationale": "Matches",
                        "evidence": ["2+2=4"],
                        "evaluator_model": model,
                    }
                ),
                "actual-provider-judge",
                {"input_tokens": 8, "output_tokens": 4},
            )

    context = {
        "prompt": "What is 2+2?",
        "judge_model": "configured-alias",
        "judge_provider": Judge(),
    }
    evaluate_rubric("factual_accuracy", "4", {"reference_evidence": "2+2=4"}, context)
    assert (
        context["rubric_evidence"]["factual_accuracy"]["evaluator_model"] == "actual-provider-judge"
    )
    assert context["judge_calls"][0]["requested_model"] == "configured-alias"
    assert context["judge_calls"][0]["usage"]["input_tokens"] == 8
