# Structured output evaluators

This module implements Omar's O1 assignment in the Prototype 2 proposal: ten
independently tested JSON evaluators. The original O1 implementation is now integrated into the combined Lina/Pranjal
Prototype 2 baseline at `e9fafc0`.

## Scope and result contract

Import from `app.evaluation.evaluators.structured`. The shared registry now
resolves these evaluators and imports their exported parameter schemas.
Every callable accepts `(response, parameters, context=None)`. The response is
text, parameters is a JSON object, and context is currently unused.

`StructuredEvaluationResult` has three fields:

| Field | Meaning |
| --- | --- |
| `passed` | Whether this individual binary check was satisfied |
| `normalized_score` | Unweighted performance: `1.0` when satisfied, `0.0` otherwise |
| `detail` | A human-readable outcome or explanation |

The result intentionally has a different type and score name from the existing
weighted `CriterionResult`. Lina's scoring layer will multiply normalized
performance by the approved criterion maximum. These evaluators do not choose
weights or calculate an overall pass threshold.

Errors are part of the integration contract:

- Invalid or noncompliant model JSON produces an ordinary result with score zero.
- An unknown criterion ID, invalid parameters, or an unusable schema raises
  `StructuredConfigurationError`.
- Evaluation failures such as excessive nesting raise `StructuredEvaluationError`.

The future dispatcher must preserve configuration/execution errors as incomplete
evaluation rather than converting them to zero points or a completed total.

## Parameter contracts

All parameters shown below are required unless the object is empty. Unknown
parameters are rejected. The module exports `PARAMETER_SCHEMAS` and
`validate_structured_parameters` for reuse by the shared registry; they are not
a separate application-wide criteria catalog.

| Criterion ID | Parameters | Check |
| --- | --- | --- |
| `valid_json` | `{}` | The complete response parses under the strict JSON profile |
| `json_object` | `{}` | The root value is an object |
| `json_array` | `{}` | The root value is an array |
| `json_required_keys` | `{"keys": ["id", "status"]}` | Every listed top-level key exists |
| `json_forbidden_keys` | `{"keys": ["secret"]}` | None of the listed top-level keys exist |
| `json_field_type` | `{"field": "count", "type": "integer"}` | A top-level field exists and has the specified JSON type |
| `json_field_value` | `{"field": "status", "value": "ready"}` | A top-level field exists and equals the expected JSON value |
| `json_array_min_length` | `{"min_length": 2}` | The root array has at least this many items |
| `json_array_max_length` | `{"max_length": 5}` | The root array has at most this many items |
| `json_schema` | `{"schema": {"type": "object", "required": ["id"]}}` | The response satisfies the supplied JSON Schema |

Key lists must contain at least one string. Array bounds must be nonnegative
integers, with zero allowed. Boolean values and floats are rejected as bounds.
Field names are literal top-level keys: `a.b` means a key named `a.b`, not a path.
Use JSON Schema for nested requirements. A present field with value `null` is
different from an absent field.

Supported field types are `object`, `array`, `string`, `number`, `integer`,
`boolean`, and `null`. JSON Schema type semantics apply: `1.0` satisfies
`integer`, but `true` does not satisfy `number` or `integer`. Value comparisons
distinguish strings from numbers and booleans from numbers, compare objects
without depending on property order, and preserve array order. Numerically
equal JSON numbers such as `1` and `1.0` compare equally.

## JSON parsing and schema behavior

The shared parser accepts surrounding whitespace, Unicode, and primitive JSON
values such as `null`, `true`, a number, or a string. It parses the entire
response and does not remove code fences or extract JSON from other prose.
The harness's stricter profile rejects duplicate object keys and nonfinite
numbers, including floating-point overflow. Duplicate-key rejection is an
intentional harness policy, not a claim that every JSON parser rejects them.

`json_schema` uses JSON Schema Draft 2020-12. An omitted `$schema` means this
draft; a different explicitly declared dialect is a configuration error.
Boolean schemas are supported. Local fragment references such as
`#/$defs/item` are supported and checked during configuration validation;
remote and filesystem references are rejected. Registry-based resolution does
not retrieve resources over the network. `format` uses the draft's default
annotation behavior, not additional email/URL enforcement. Use explicit schema
constraints or the appropriate future pattern evaluator for such checks.

The JSON Schema library implements schema evaluation. References:

- https://python-jsonschema.readthedocs.io/en/stable/validate/
- https://python-jsonschema.readthedocs.io/en/stable/referencing/

## Run locally in PowerShell

From the repository root, with Python 3.12's virtual environment active:

```powershell
Set-Location .\backend
python -m pip install -e ".[dev]"
python -m pytest tests/test_structured_evaluators.py -q
python -m ruff check app/evaluation/evaluators tests/test_structured_evaluators.py
python -m ruff format --check app/evaluation/evaluators tests/test_structured_evaluators.py
```

The evaluator tests require no PostgreSQL service or model API credentials.
An optional smoke check from the same backend directory:

```powershell
@'
from dataclasses import asdict
from app.evaluation.evaluators.structured import evaluate_structured

for response in ['{"count": 3}', '{"count": "three"}']:
    result = evaluate_structured(
        "json_field_type", response, {"field": "count", "type": "integer"}
    )
    print(response, asdict(result))
'@ | python
```

The first response earns `1.0`; the second earns `0.0`.

## Integration status

All ten IDs are selectable through the registry-backed criteria API and browser
editor. The dispatcher adapts these normalized result objects to the common
criterion result contract and applies user allocations. O2 storage preserves the
approved parameters, points and prompt configuration on immutable run snapshots.
The original six-check path remains available for compatibility. See
[Prototype 2 integration](prototype2-integration.md) and
[local review steps](prototype2-local-review.md) for the complete workflow.
