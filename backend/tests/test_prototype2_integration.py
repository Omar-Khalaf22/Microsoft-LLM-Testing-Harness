"""Prototype 2 integration coverage that can run before every piece has landed.

Three groups live here:

* Prototype 1 regression: the original six-criterion workflow through the real HTTP route, with
  the model provider replaced by a fake. Runs on any branch without a database.
* Registry and dispatcher: unsupported IDs, invalid parameters, executable-versus-planned
  invariants, and weighted scoring checked against hand-calculated totals. These need the
  criteria registry and dispatcher (``app.evaluation.registry`` / ``validators``) and skip until
  those modules are on the branch.
* Placeholders for behavior that depends on code nobody has merged yet (assistant endpoint,
  ``criteria`` on ``POST /runs``, configuration persistence). They are skipped with the owner
  and dependency named, so the remaining checklist stays visible.

No test here reaches a real model: ``urlopen`` is replaced with a guard that fails loudly.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.evaluation import executor as executor_module
from app.evaluation import providers
from app.evaluation.evaluators.patterns import EVALUATORS
from app.evaluation.providers import OpenAICompatibleProvider, ProviderResponse
from app.evaluation.repository import JsonResultRepository
from app.evaluation.scoring import score_response

try:
    from app.evaluation.validators import evaluate_selected

    from app.evaluation import registry
except ImportError:  # The registry and dispatcher have not been merged onto this branch yet.
    registry = None
    evaluate_selected = None

needs_registry = pytest.mark.skipif(
    registry is None,
    reason="Criteria registry and dispatcher (Lina, prototype-2-lina) are not on this branch",
)

LEGACY_CRITERIA = [
    "Keyword coverage",
    "Prompt relevance",
    "Minimum length",
    "Sentence structure",
    "Forbidden terms",
    "Valid response",
]
DEFAULT_WEIGHTS = {
    "keyword": 30,
    "relevance": 20,
    "length": 15,
    "sentences": 15,
    "forbidden": 10,
    "valid": 10,
}
MODEL_TEXT = (
    "A multiplexer does one simple job: it selects one input and sends it to the output. "
    "The select lines choose which input is used. It is a common digital building block."
)


class FakeProvider:
    """Deterministic stand-in for a model endpoint; records every call it receives."""

    name = "fake_model"

    def __init__(self, text: str = MODEL_TEXT, error: Exception | None = None):
        self.text = text
        self.error = error
        self.calls: list[dict] = []

    def generate(self, prompt, model, temperature, **options):
        self.calls.append({"prompt": prompt, "model": model, "temperature": temperature, **options})
        if self.error is not None:
            raise self.error
        return ProviderResponse(
            text=self.text, model=model, usage={"input_tokens": 12, "output_tokens": 34}
        )


@pytest.fixture(autouse=True)
def no_real_model_calls(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("A test attempted a real network request to a model endpoint")

    monkeypatch.setattr(providers, "urlopen", refuse)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """The real FastAPI app with the executor swapped for a fake provider and a JSON file."""
    if "DATABASE_URL" not in os.environ:
        monkeypatch.setenv(
            "DATABASE_URL", "postgresql+psycopg://llm_harness:test@localhost:5432/llm_harness_test"
        )
    from app.main import app
    from app.routes.runs import get_executor

    provider = FakeProvider()
    repository = JsonResultRepository(tmp_path / "results.jsonl")
    app.dependency_overrides[get_executor] = lambda: executor_module.TestExecutor(
        provider, repository
    )
    try:
        yield TestClient(app), provider, repository
    finally:
        app.dependency_overrides.pop(get_executor, None)


def legacy_request(**overrides):
    body = {
        "test_name": "Prototype 1 regression",
        "prompt": "Explain what a multiplexer does.",
        "model": "gpt-4.1-mini",
        "temperature": 0.2,
        "expected_keywords": ["multiplexer", "select"],
        "forbidden_terms": ["error"],
        "minimum_length": 20,
        "minimum_sentences": 2,
        "weights": dict(DEFAULT_WEIGHTS),
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------------------------
# Prototype 1 regression (real HTTP route, fake model, no database)
# ---------------------------------------------------------------------------------------------


def test_legacy_request_still_runs_the_six_original_criteria(harness):
    client, provider, repository = harness
    response = client.post("/runs", json=legacy_request())

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["criteria"]] == LEGACY_CRITERIA
    assert body["score"] == 100
    assert body["passed"] is True
    assert body["status"] == "completed"
    assert body["provider"] == "fake_model"
    assert body["response"] == MODEL_TEXT
    assert body["metadata"]["usage"] == {"input_tokens": 12, "output_tokens": 34}
    assert len(provider.calls) == 1
    assert len(repository.recent()) == 1


def test_legacy_http_result_matches_the_scoring_function_directly(harness):
    client, _provider, _repository = harness
    request = legacy_request(expected_keywords=["multiplexer", "missing term"], minimum_length=500)
    body = client.post("/runs", json=request).json()

    expected_score, expected_criteria = score_response(
        request["prompt"],
        MODEL_TEXT,
        request["expected_keywords"],
        request["minimum_length"],
        request["minimum_sentences"],
        request["forbidden_terms"],
        request["weights"],
    )
    assert body["score"] == expected_score
    assert [item["score"] for item in body["criteria"]] == [c.score for c in expected_criteria]
    assert [item["passed"] for item in body["criteria"]] == [c.passed for c in expected_criteria]
    assert body["passed"] is (expected_score >= 75)
    assert body["score"] < 100


def test_custom_legacy_weights_are_applied(harness):
    client, _provider, _repository = harness
    weights = {**DEFAULT_WEIGHTS, "keyword": 50, "relevance": 10, "length": 10, "sentences": 10}
    request = legacy_request(expected_keywords=["multiplexer", "missing term"], weights=weights)
    body = client.post("/runs", json=request).json()

    keyword = next(item for item in body["criteria"] if item["name"] == "Keyword coverage")
    assert keyword["passed"] is False
    assert keyword["score"] == 25.0  # one of two keywords matched, out of 50 points
    assert body["metadata"]["scoring_weights"] == weights


def test_forbidden_term_in_the_response_costs_its_points(harness):
    client, provider, _repository = harness
    provider.text = MODEL_TEXT + " An error occurred."
    body = client.post("/runs", json=legacy_request()).json()

    forbidden = next(item for item in body["criteria"] if item["name"] == "Forbidden terms")
    assert forbidden["passed"] is False
    assert forbidden["score"] == 0
    assert body["score"] == 90


@pytest.mark.parametrize(
    "mutation",
    [
        {"weights": {**DEFAULT_WEIGHTS, "keyword": 40}},
        {"weights": {**DEFAULT_WEIGHTS, "keyword": -5, "valid": 25}},
        {"weights": {**DEFAULT_WEIGHTS, "surprise": 0}},
        {"bogus_field": "not part of the contract"},
        {"test_name": ""},
        {"prompt": "   "},
        {"temperature": 3},
        {"model": ""},
        {"minimum_sentences": 0},
    ],
)
def test_invalid_legacy_requests_are_rejected_before_any_model_call(harness, mutation):
    client, provider, repository = harness
    response = client.post("/runs", json=legacy_request(**mutation))

    assert response.status_code == 422
    assert provider.calls == []
    assert repository.recent() == []


def test_provider_failure_returns_a_sanitized_error(harness):
    client, provider, repository = harness
    provider.error = RuntimeError("upstream said: api key sk-secret-123 is invalid")
    response = client.post("/runs", json=legacy_request())

    assert response.status_code == 500
    assert response.json() == {"detail": "The run could not be completed."}
    assert "sk-secret" not in response.text
    assert repository.recent() == []


def test_model_call_guard_blocks_real_endpoints():
    provider = OpenAICompatibleProvider(api_key="unused", base_url="https://example.invalid/v1")
    with pytest.raises(AssertionError, match="real network request"):
        provider.generate("hello", "gpt-4.1-mini", 0.2)


# ---------------------------------------------------------------------------------------------
# Registry: unsupported IDs, invalid parameters, planned versus supported
# ---------------------------------------------------------------------------------------------

SUGGESTION = {
    "criterion_id": "required_keywords",
    "parameters": {"keywords": ["PMOS", "NMOS"]},
    "weight": 40,
    "reason": "The objective names two transistor types.",
}


@needs_registry
def test_a_valid_assistant_suggestion_passes_registry_validation():
    item = registry.validate_criterion(SUGGESTION["criterion_id"], SUGGESTION["parameters"])
    assert item["status"] == "supported"
    assert item["id"] == "required_keywords"


@needs_registry
@pytest.mark.parametrize("criterion_id", ["", "made_up_criterion", "REQUIRED_KEYWORDS", "../etc"])
def test_unsupported_ids_are_rejected(criterion_id):
    with pytest.raises(ValueError, match="Unknown criterion ID"):
        registry.validate_criterion(criterion_id, {"keywords": ["a"]})


@needs_registry
@pytest.mark.parametrize(
    ("criterion_id", "parameters"),
    [
        ("required_keywords", {}),
        ("required_keywords", {"keywords": []}),
        ("required_keywords", {"keywords": ["ok", ""]}),
        ("required_keywords", {"keywords": ["ok", 3]}),
        ("required_keywords", {"keywords": "PMOS"}),
        ("required_keywords", {"keywords": ["ok"], "extra": 1}),
        ("required_keywords", ["PMOS"]),
        ("required_keywords", None),
        ("exact_match", {"expected": 5}),
        ("minimum_characters", {"count": -1}),
        ("minimum_characters", {"count": 2.5}),
        ("minimum_characters", {"count": True}),
        ("minimum_characters", {"count": "3"}),
        ("minimum_sentences", {"count": 0}),
    ],
)
def test_invalid_parameters_are_rejected(criterion_id, parameters):
    with pytest.raises(ValueError):
        registry.validate_criterion(criterion_id, parameters)


CATALOG = registry.catalog() if registry is not None else []
SUPPORTED = [item for item in CATALOG if item["status"] == "supported"]
PLANNED = [item for item in CATALOG if item["status"] == "planned"]
SAMPLE_VALUES = {"list[str]": ["alpha"], "str": "alpha", "int": 1}


def sample_parameters(item):
    unknown = [kind for kind in item["parameters"].values() if kind not in SAMPLE_VALUES]
    assert not unknown, f"{item['id']}: add sample values for parameter kind(s) {unknown}"
    return {name: SAMPLE_VALUES[kind] for name, kind in item["parameters"].items()}


@needs_registry
def test_catalog_entries_are_well_formed_and_unique():
    ids = [item["id"] for item in CATALOG]
    assert len(ids) == len(set(ids))
    required = {"id", "name", "category", "description", "evaluator", "parameters", "status"}
    for item in CATALOG:
        assert required <= set(item), item["id"]
        assert item["status"] in {"planned", "supported"}, item["id"]
        if item["status"] == "supported":
            assert item["evaluator"], f"{item['id']} is supported but names no evaluator"


@needs_registry
@pytest.mark.parametrize("item", SUPPORTED, ids=[item["id"] for item in SUPPORTED])
def test_every_supported_criterion_is_actually_executable(item):
    """A criterion may only be advertised as supported if the dispatcher can run it."""
    score, results = evaluate_selected(
        "alpha beta gamma. Delta epsilon.",
        [{"id": item["id"], "parameters": sample_parameters(item), "weight": 100}],
    )
    assert 0 <= score <= 100
    assert [result["id"] for result in results] == [item["id"]]


@needs_registry
@pytest.mark.parametrize("item", PLANNED, ids=[item["id"] for item in PLANNED])
def test_planned_criteria_cannot_be_executed(item):
    with pytest.raises(ValueError, match="not executable"):
        registry.validate_criterion(item["id"], {})
    with pytest.raises(ValueError):
        evaluate_selected(
            "any response",
            [{"id": item["id"], "parameters": {}, "weight": 100}],
        )


@needs_registry
def test_supported_listing_matches_the_catalog():
    listed = {item["id"] for item in registry.list_supported_criteria()}
    assert listed == {item["id"] for item in SUPPORTED}


# ---------------------------------------------------------------------------------------------
# Dispatcher: execution of approved criteria
# ---------------------------------------------------------------------------------------------

TWO_SENTENCES = "Hello world. Second sentence."


@needs_registry
def test_overall_score_equals_the_hand_calculated_weighted_total():
    # exact_match 25 + minimum_characters 25 + minimum_sentences 2/4 of 30 + forbidden 20 = 85
    score, results = evaluate_selected(
        TWO_SENTENCES,
        [
            {"id": "exact_match", "parameters": {"expected": TWO_SENTENCES}, "weight": 25},
            {"id": "minimum_characters", "parameters": {"count": 10}, "weight": 25},
            {"id": "minimum_sentences", "parameters": {"count": 4}, "weight": 30},
            {"id": "forbidden_keywords", "parameters": {"keywords": ["secret"]}, "weight": 20},
        ],
    )
    assert score == 85.0
    assert [result["score"] for result in results] == [25.0, 25.0, 15.0, 20.0]
    assert [result["passed"] for result in results] == [True, True, False, True]
    assert sum(result["score"] for result in results) == score


@needs_registry
def test_each_criterion_is_evaluated_separately_and_in_request_order():
    approved = [
        {"id": "minimum_characters", "parameters": {"count": 10}, "weight": 50},
        {"id": "exact_match", "parameters": {"expected": "other"}, "weight": 50},
    ]
    score, results = evaluate_selected("abcd", approved)

    assert [result["id"] for result in results] == ["minimum_characters", "exact_match"]
    assert results[0]["normalized_score"] == pytest.approx(0.4)
    assert results[0]["score"] == 20.0
    assert results[1]["normalized_score"] == 0
    assert results[1]["passed"] is False
    assert score == 20.0


@needs_registry
def test_partial_credit_is_rounded_to_one_decimal():
    score, results = evaluate_selected(
        "Only one sentence.",
        [{"id": "minimum_sentences", "parameters": {"count": 3}, "weight": 100}],
    )
    assert results[0]["score"] == 33.3
    assert score == 33.3


@needs_registry
def test_frontend_approved_criteria_payload_is_accepted_by_the_dispatcher():
    """Mirrors how the browser maps a suggestion to an approved criterion (id/parameters/weight)."""
    suggestions = [
        {**SUGGESTION, "weight": 68.75},
        {
            "criterion_id": "maximum_characters",
            "parameters": {"count": 500},
            "weight": 31.25,
            "reason": "Keep the answer short.",
        },
    ]
    approved = [
        {"id": s["criterion_id"], "parameters": s["parameters"], "weight": s["weight"]}
        for s in suggestions
    ]
    score, results = evaluate_selected("PMOS and NMOS transistors.", approved)

    assert score == 100.0
    assert [result["passed"] for result in results] == [True, True]


@needs_registry
def test_suggestion_fields_beyond_id_parameters_weight_must_be_stripped_before_running():
    with pytest.raises(ValueError, match="id, parameters and weight"):
        evaluate_selected(
            "PMOS NMOS",
            [
                {
                    "id": "required_keywords",
                    "parameters": {"keywords": ["PMOS"]},
                    "weight": 100,
                    "reason": "left over from the assistant",
                }
            ],
        )


@needs_registry
@pytest.mark.parametrize(
    "weights",
    [(50, 49.9), (60, 60), (50, 50.1), (-10, 110), (0, 99), (101, -1)],
)
def test_weights_must_total_exactly_one_hundred(weights):
    approved = [
        {"id": "contains_text", "parameters": {"text": "a"}, "weight": weights[0]},
        {"id": "exact_match", "parameters": {"expected": "a"}, "weight": weights[1]},
    ]
    with pytest.raises(ValueError):
        evaluate_selected("a", approved)


@needs_registry
@pytest.mark.parametrize("weight", [True, "50", None, float("nan"), float("inf"), -1, 100.5])
def test_each_weight_must_be_a_finite_number_between_zero_and_one_hundred(weight):
    with pytest.raises(ValueError):
        evaluate_selected(
            "a", [{"id": "exact_match", "parameters": {"expected": "a"}, "weight": weight}]
        )


@needs_registry
def test_selection_level_errors_are_rejected():
    ok = {"id": "exact_match", "parameters": {"expected": "a"}, "weight": 100}
    with pytest.raises(ValueError, match="At least one"):
        evaluate_selected("a", [])
    with pytest.raises(ValueError, match="Too many"):
        evaluate_selected("a", [ok] * 101)
    with pytest.raises(ValueError, match="unique"):
        evaluate_selected("a", [{**ok, "weight": 50}, {**ok, "weight": 50}])
    with pytest.raises(ValueError, match="id, parameters and weight"):
        evaluate_selected("a", [{"id": "exact_match", "weight": 100}])
    with pytest.raises(ValueError, match="id, parameters and weight"):
        evaluate_selected("a", ["exact_match"])
    with pytest.raises(ValueError, match="unique"):
        evaluate_selected("a", [{**ok, "id": 7}])


@needs_registry
def test_unsupported_and_planned_ids_fail_the_whole_selection():
    good = {"id": "exact_match", "parameters": {"expected": "a"}, "weight": 50}
    for bad_id in ("not_a_criterion", "semantic_similarity"):
        with pytest.raises(ValueError):
            evaluate_selected("a", [good, {"id": bad_id, "parameters": {}, "weight": 50}])


@needs_registry
def test_dispatcher_does_not_use_the_legacy_six_score_fields():
    score, results = evaluate_selected(
        "a b",
        [{"id": "contains_text", "parameters": {"text": "a"}, "weight": 100}],
    )
    legacy = {name.casefold() for name in LEGACY_CRITERIA}
    assert score == 100.0
    assert all(result["id"].replace("_", " ") not in legacy for result in results)


# ---------------------------------------------------------------------------------------------
# Pattern/numeric evaluators (patterns.py) alongside the registry
# ---------------------------------------------------------------------------------------------

PATTERN_EXAMPLES = {
    "regex_match": ({"pattern": r"\d+"}, "order 42 shipped"),
    "regex_not_match": ({"pattern": r"password"}, "all clear"),
    "email_format": ({}, "write to bob@example.com"),
    "url_format": ({}, "see https://example.com/docs"),
    "numeric_exact": ({"expected": 42}, "The answer is 42."),
    "numeric_range": ({"minimum": 1, "maximum": 10}, "about 7 units"),
    "numeric_tolerance": ({"expected": 100, "tolerance": 2}, "roughly 101"),
    "word_count_min": ({"minimum": 3}, "one two three four"),
    "word_count_max": ({"maximum": 5}, "one two three"),
    "required_sections": ({"sections": ["Summary"]}, "# Summary\nAll good."),
}


def test_the_ten_pattern_evaluators_pass_their_documented_examples():
    assert set(PATTERN_EXAMPLES) == set(EVALUATORS)
    for criterion_id, (parameters, response) in PATTERN_EXAMPLES.items():
        result = EVALUATORS[criterion_id](response, parameters)
        assert result.passed, f"{criterion_id}: {result.detail}"
        assert result.score == 1.0


@needs_registry
def test_pattern_criteria_are_listed_in_the_catalog():
    cataloged = {item["id"] for item in CATALOG}
    assert set(EVALUATORS) <= cataloged


@needs_registry
@pytest.mark.xfail(
    reason=(
        "Pattern criteria are still 'planned' in the catalog with no parameter schema, and the "
        "dispatcher only routes to the content evaluators. The registry's validator also only "
        "understands list[str]/str/int with no optional parameters; regex flags, numbers and "
        "enums need new parameter kinds. Needs agreement between Lina and Ahmad."
    ),
    strict=False,
)
@pytest.mark.parametrize("criterion_id", sorted(PATTERN_EXAMPLES))
def test_pattern_criteria_execute_through_the_dispatcher(criterion_id):
    parameters, response = PATTERN_EXAMPLES[criterion_id]
    score, results = evaluate_selected(
        response, [{"id": criterion_id, "parameters": parameters, "weight": 100}]
    )
    assert score == 100.0
    assert results[0]["passed"] is True


# ---------------------------------------------------------------------------------------------
# Not testable yet: each placeholder names the missing piece and who owns it
# ---------------------------------------------------------------------------------------------


@pytest.mark.skip(reason="Needs POST /assistant/suggest-criteria (Pranjal; no branch has it yet)")
def test_assistant_returns_valid_registry_criteria_with_reasons(harness):
    """Mock the assistant model; expect criterion_id, parameters, weight and reason per item,
    every ID supported by the registry, and weights totaling 100."""


@pytest.mark.skip(reason="Needs POST /assistant/suggest-criteria (Pranjal; no branch has it yet)")
def test_assistant_rejects_unsupported_ids_bad_parameters_and_malformed_output(harness):
    """Mock model output containing unknown IDs, planned-only IDs, wrong parameter types, missing
    parameters, bad weight totals and non-JSON text; expect none of it returned as executable."""


@pytest.mark.skip(
    reason="Needs a `criteria` field on POST /runs wired to the dispatcher (Lina/Pranjal)"
)
def test_run_endpoint_executes_approved_criteria_and_returns_their_results(harness):
    """POST /runs with approved criteria and a fake provider; expect per-criterion results and
    an overall score equal to the dispatcher's hand-calculated total, and no legacy-six results."""


@pytest.mark.skip(
    reason="Needs migration 0004 and criteria persistence (Omar) plus PostgreSQL in CI"
)
def test_approved_criteria_and_weights_are_saved_and_retrieved_exactly(harness):
    """Run with approved criteria, reload from the database, and compare the stored configuration
    (IDs, parameters, weights, generated-versus-approved state) with what was submitted, even after
    the test is later edited."""
