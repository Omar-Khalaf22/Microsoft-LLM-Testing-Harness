"""Evidence grounded semantic rubric execution and safety tests."""

import json

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion

IDS = (
    "semantic_similarity",
    "factual_consistency",
    "citation_accuracy",
    "hallucination_detection",
    "source_attribution",
    "answer_relevance",
    "translation_accuracy",
    "summarization_coverage",
)


class Judge:
    name = "test_judge"

    def generate(self, prompt, model, temperature, system_prompt):
        from app.evaluation.providers import ProviderResponse

        payload = json.loads(prompt)
        assert payload["criterion_id"] in IDS
        assert payload["reference_evidence"] == "Verified source statement."
        return ProviderResponse(
            text=json.dumps(
                {
                    "score": 0.9,
                    "rationale": "The response is consistent with the supplied reference.",
                    "evidence": ["Verified source statement."],
                    "evaluator_model": model,
                }
            ),
            model=model,
            usage={},
        )


@pytest.mark.parametrize("criterion_id", IDS)
def test_semantic_criteria_execute_with_reference(criterion_id):
    context = {
        "prompt": "Explain the verified statement",
        "judge_provider": Judge(),
        "judge_model": "test_model",
    }
    passed, score, detail = evaluate_criterion(
        criterion_id,
        "Verified source statement.",
        {"reference_evidence": "Verified source statement."},
        context,
    )
    assert passed is True
    assert score == pytest.approx(0.9)
    assert detail
    assert context["rubric_evidence"][criterion_id]["evidence"] == ["Verified source statement."]


@pytest.mark.parametrize("criterion_id", IDS)
def test_semantic_criteria_reject_missing_reference(criterion_id):
    with pytest.raises(ValueError, match="reference_evidence.*required property"):
        validate_criterion(criterion_id, {})


@pytest.mark.parametrize("criterion_id", IDS)
def test_semantic_criteria_require_real_judge_configuration(criterion_id):
    with pytest.raises(RuntimeError, match="not configured"):
        evaluate_criterion(
            criterion_id,
            "answer",
            {"reference_evidence": "Verified source statement."},
            {"prompt": "question"},
        )
