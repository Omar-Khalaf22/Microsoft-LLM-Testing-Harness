"""Audit catalog registration and evaluator contracts.

These tests check structural readiness, not semantic correctness or sandbox safety.
"""

from collections import Counter

from jsonschema import Draft202012Validator

from app.evaluation import registry


def test_catalog_has_exactly_112_unique_criteria():
    items = registry.catalog()
    assert len(items) == 112
    counts = Counter(item["id"] for item in items)
    assert all(count == 1 for count in counts.values())


def test_supported_criteria_have_registered_evaluators():
    for item in registry.list_supported_criteria():
        assert item["evaluator_type"] in registry._EVALUATORS
        assert callable(registry._EVALUATORS[item["evaluator_type"]])


def test_all_parameter_schemas_are_valid():
    for item in registry.catalog():
        Draft202012Validator.check_schema(item["parameter_schema"])


def test_supported_examples_validate():
    for item in registry.list_supported_criteria():
        parameters = item.get("example_parameters")
        if parameters is None:
            continue
        registry.validate_criterion(item["id"], parameters)


def test_execution_evidence_requires_external_integration():
    for criterion_id in ("code_execution", "unit_test_pass"):
        item = registry.get_criterion(criterion_id)
        assert item["evaluator_type"] == "execution_evidence"
        assert "external" in item["method_status"].lower()
