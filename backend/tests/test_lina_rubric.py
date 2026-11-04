"""Prototype 3 rubric tests use a fake judge, never paid model calls."""

import json
import math

import pytest

from app.evaluation.rubric_integration import evaluate_rubric
from app.evaluation.rubric_judge import InvalidJudgment, judge_rubric

BASE = {
    "criterion_id": "factual_accuracy",
    "prompt": "What is 2+2?",
    "response": "4",
    "reference_evidence": "2+2=4",
    "evaluator_model": "judge-test",
}


def valid(payload):
    return {
        "score": 1.0,
        "rationale": "Matches the reference",
        "evidence": ["2+2=4"],
        "evaluator_model": payload["evaluator_model"],
    }


def test_strong_response():
    assert judge_rubric(**BASE, invoke=valid).normalized_score == 1


def test_weak_response():
    result = judge_rubric(**BASE, invoke=lambda p: dict(valid(p), score=0.2))
    assert result.normalized_score == 0.2


def test_misleading_response():
    assert judge_rubric(**BASE, invoke=lambda p: dict(valid(p), score=0)).normalized_score == 0


@pytest.mark.parametrize("score", [-0.1, 1.1, math.nan, math.inf, "0.7", True])
def test_invalid_scores(score):
    with pytest.raises(InvalidJudgment):
        judge_rubric(**BASE, invoke=lambda p: dict(valid(p), score=score))


def test_missing_rationale():
    with pytest.raises(InvalidJudgment):
        judge_rubric(**BASE, invoke=lambda p: dict(valid(p), rationale=""))


def test_model_mismatch():
    with pytest.raises(InvalidJudgment):
        judge_rubric(**BASE, invoke=lambda p: dict(valid(p), evaluator_model="other"))


def test_fabricated_evidence():
    with pytest.raises(InvalidJudgment):
        judge_rubric(**BASE, invoke=lambda p: dict(valid(p), evidence=["fabricated"]))


class FakeProvider:
    def __init__(self, score=1, text=None):
        self.score, self.text = score, text

    def generate(self, prompt, model, temperature, system_prompt):
        class Output:
            pass

        result = Output()
        result.model = model
        result.text = (
            self.text
            if self.text is not None
            else json.dumps(
                {
                    "score": self.score,
                    "rationale": "Based on supplied evidence",
                    "evidence": ["2+2=4"],
                    "evaluator_model": model,
                }
            )
        )
        return result


@pytest.mark.parametrize("criterion", ["factual_accuracy", "completeness", "evidence_grounding"])
def test_supported_criteria(criterion):
    context = {"prompt": "2+2?", "judge_provider": FakeProvider(), "judge_model": "judge-test"}
    passed, score, detail = evaluate_rubric(
        criterion, "4", {"reference_evidence": "2+2=4"}, context
    )
    assert passed and score == 1
    assert context["rubric_evidence"][criterion]["evaluator_model"] == "judge-test"


@pytest.mark.parametrize("score,passed", [(0.1, False), (0.5, False), (0.8, True)])
def test_quality_levels(score, passed):
    context = {"prompt": "2+2?", "judge_provider": FakeProvider(score), "judge_model": "judge-test"}
    assert evaluate_rubric(
        "factual_accuracy", "wrong", {"reference_evidence": "2+2=4"}, context
    )[0] is passed


@pytest.mark.parametrize("text", ["not json", "{}", '{"score":5}', "[]"])
def test_malformed_judgment(text):
    context = {
        "prompt": "2+2?",
        "judge_provider": FakeProvider(text=text),
        "judge_model": "judge-test",
    }
    with pytest.raises((ValueError, TypeError)):
        evaluate_rubric("factual_accuracy", "wrong", {"reference_evidence": "2+2=4"}, context)
