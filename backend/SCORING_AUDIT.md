# Scoring criteria audit

## Scope

The catalog contains 112 unique criterion IDs. All 112 currently have status
`supported`. Registration is not proof of complete scoring capability.

## Automated structural checks

Run from `backend`:

```bash
ruff check .
ruff format --check .
pytest -v
python -m app.storage.schema --check
```

The audit test module checks catalog uniqueness, registered evaluator functions,
valid JSON Schemas, and example parameter validation.

## Known gaps requiring implementation

1. `code_execution` does not execute candidate code. It only scores a result
   provided through `context.execution_result`. A trusted isolated execution
   service, resource limits, language support, timeout handling, and evidence
   binding must be implemented before claiming complete code execution support.
2. `unit_test_pass` does not execute test cases. It only scores supplied
   results. It requires the same isolated execution integration.
3. The `trusted: true` value in execution evidence is a caller supplied flag.
   It does not authenticate evidence provenance and must not be treated as
   security proof.
4. `clarity` uses sentence word limits. `coherence` uses exact normalized
   sentence uniqueness. Neither establishes semantic clarity or coherence.
5. `prompt_injection_resistance` and `jailbreak_resistance` use configured
   response phrases. They do not establish general attack resistance.
6. `reasoning_consistency` detects configured phrase pairs, not logical
   contradictions in arbitrary language.
7. `toxicity`, `bias`, and `safety_policy` use configured phrase lists,
   not general safety classification.

## Release criteria

Do not claim 112 fully supported criteria until the GitHub Actions workflow
passes on the target commit, each criterion has positive and negative behavioral
tests, each evaluator is tested through the public API, and external execution
and semantic evaluation limitations are either implemented or explicitly
represented as limited capabilities.

This document is an implementation audit, not a certification that all checks
have passed.
