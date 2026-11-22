"""Catalog wide regression checks for all supported scoring criteria."""

import pytest

from app.evaluation.registry import (
    _EVALUATORS,
    catalog,
    get_criterion,
    list_supported_criteria,
    validate_criterion,
)


@pytest.fixture(scope="module")
def definitions():
    return catalog()


def test_catalog_has_unique_identifiers(definitions):
    ids = [item["id"] for item in definitions]
    assert len(ids) == 112
    assert len(ids) == len(set(ids))


def test_supported_catalog_entries_have_registered_evaluators(definitions):
    supported = list_supported_criteria()
    assert len(supported) == len(definitions)
    for item in supported:
        assert item["status"] == "supported", item["id"]
        assert item["evaluator_type"] in _EVALUATORS, item["id"]
        assert callable(_EVALUATORS[item["evaluator_type"]]), item["id"]


@pytest.mark.parametrize(
    "criterion_id",
    [item["id"] for item in catalog()],
)
def test_catalog_example_parameters_validate(criterion_id):
    item = get_criterion(criterion_id)
    assert isinstance(item["example_parameters"], dict)
    validated = validate_criterion(criterion_id, item["example_parameters"])
    assert validated["id"] == criterion_id


@pytest.mark.parametrize(
    "criterion_id",
    [item["id"] for item in catalog()],
)
def test_catalog_rejects_non_object_parameters(criterion_id):
    with pytest.raises(ValueError):
        validate_criterion(criterion_id, None)
