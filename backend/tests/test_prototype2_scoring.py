from pydantic import ValidationError
import pytest
from app.prototype2.scoring import ScoringConfiguration, evaluate

def config(rows):
    return ScoringConfiguration(criteria=rows)

def test_exact_total():
    for value in ("99.99", "100.01"):
        with pytest.raises(ValidationError):
            config([{"id": "nonempty", "points": value}])
    assert config([{"id": "nonempty", "points": "100.00"}])

def test_duplicate_and_unsupported():
    with pytest.raises(ValidationError):
        config([{"id": "nonempty", "points": "50"}, {"id": "nonempty", "points": "50"}])
    with pytest.raises(ValidationError):
        config([{"id": "invented", "points": "100"}])

def test_json_scoring():
    cfg = config([{"id": "valid_json", "points": "40"}, {"id": "required_keys", "points": "60", "parameters": {"keys": ["name", "age"]}}])
    assert evaluate(cfg, '{"name":"Lina"}')["total"] == "70.00"
    assert evaluate(cfg, "not json")["total"] == "0.00"

def test_type_and_empty():
    cfg = config([{"id": "field_types", "points": "70", "parameters": {"types": {"active": "boolean", "age": "number"}}}, {"id": "nonempty", "points": "30"}])
    assert evaluate(cfg, '{"active":true,"age":21}')["total"] == "100.00"
    assert evaluate(cfg, "")["total"] == "0.00"
