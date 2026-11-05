# Lina Prototype 3: rubric scoring and human reviews

This integrated branch supports `factual_accuracy` and `evidence_grounding` through
the registry/API, for 38 supported criteria in total. `completeness` remains planned
in the registry; its direct helper tests do not establish an executable API path.

## Rubric scoring

Select rubric criteria with nonempty `reference_evidence` as a prerequisite. All selected
criteria weights must still total 100.00. The executor sends the approved system instructions,
prompt, response and reference evidence to a separately configured judge model
(`JUDGE_MODEL`, `JUDGE_PROFILE_ID`, `JUDGE_PROFILE_REVISION`, plus private provider
configuration or an injected judge context). `ASSISTANT_MODEL` remains the recommendation
role. The judge returns a JSON
score from 0 to 1, rationale, verbatim reference excerpts and evaluator model identity.
Invalid, missing, or out of range judgments leave the automatic total null. The
per criterion response and saved evaluation evidence include model, rationale and excerpts.

This implementation does not claim that an LLM judgment proves factual correctness.
The rubric score is an assessment based on the supplied reference and judge behavior.
A live API key is required for live subjective scoring; demo mode cannot fabricate a judge.

## Human review API

`POST /runs/{run_id}/reviews` accepts:
```json
{"rating":80,"rationale":"Clear but missing a citation"}
```
`GET /runs/{run_id}/reviews` returns every revision in chronological order.
Each review includes ID, run ID, reviewer ID, rating, rationale, revision and timestamp.
Earlier revisions are retained. Neither endpoint modifies automated run totals.
Apply through `0006_omar_storage`, following `0005_lina_reviews`, for this integrated
branch. Reviewer identity is server-derived; an old client's reviewer_id field is
accepted for compatibility and ignored as identity. Imported attribution is explicit.

## Integration handoffs

Pranjal: confirm evaluator model configuration and model call contract.
Omar: confirm human review migration and transaction/locking contract.
Ahmad: use the two review endpoints and display human ratings separately.
PostgreSQL persistence, concurrency and verified-JWT rejection tests pass locally.
Live judge discrimination, real issuer/browser login, and deployed integration remain
externally unverified. See the P3 storage handoff and requirements/status documents.
