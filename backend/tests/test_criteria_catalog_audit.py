"""Fast, parametrized catalog contract tests for all scoring criteria.

These tests verify registration and input validation, not semantic accuracy.
"""

from collections import Counter
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from app.evaluation import registry

CRITERIA = registry.catalog()
SUPPORTED = [item for item in CRITERIA if item["status"] == "supported"]
IDS = [item["id"] for item in SUPPORTED]


def test_catalog_has_exactly_112_unique_criteria():
    assert len(CRITERIA) == 112
    counts = Counter(item["id"] for item in CRITERIA)
    assert all(count == 1 for count in counts.values())


@pytest.mark.parametrize("item", SUPPORTED, ids=IDS)
def test_supported_criterion_has_registered_evaluator(item):
    assert item["evaluator_type"] in registry._EVALUATORS
    assert callable(registry._EVALUATORS[item["evaluator_type"]])


@pytest.mark.parametrize("item", CRITERIA, ids=[item["id"] for item in CRITERIA])
def test_parameter_schema_is_valid(item):
    Draft202012Validator.check_schema(item["parameter_schema"])


@pytest.mark.parametrize("item", SUPPORTED, ids=IDS)
def test_example_parameters_validate(item):
    assert "example_parameters" in item
    registry.validate_criterion(item["id"], deepcopy(item["example_parameters"]))


@pytest.mark.parametrize("item", SUPPORTED, ids=IDS)
def test_non_object_parameters_are_rejected(item):
    with pytest.raises(ValueError):
        registry.validate_criterion(item["id"], None)


@pytest.mark.parametrize("item", SUPPORTED, ids=IDS)
def test_unexpected_parameters_are_rejected_when_schema_is_closed(item):
    schema = item["parameter_schema"]
    if schema.get("additionalProperties") is not False:
        pytest.skip("Schema permits additional properties")
    parameters = deepcopy(item["example_parameters"])
    parameters["__unexpected_test_parameter__"] = True
    with pytest.raises(ValueError):
        registry.validate_criterion(item["id"], parameters)


@pytest.mark.parametrize("item", SUPPORTED, ids=IDS)
def test_example_parameters_are_not_mutated_by_validation(item):
    parameters = deepcopy(item["example_parameters"])
    original = deepcopy(parameters)
    registry.validate_criterion(item["id"], parameters)
    assert parameters == original


def test_execution_evidence_requires_external_integration():
    for criterion_id in ("code_execution", "unit_test_pass"):
        item = registry.get_criterion(criterion_id)
        assert item["evaluator_type"] == "execution_evidence"
        assert "external" in item["method_status"].lower()
