# Lina Prototype 3: rubric scoring and human reviews

This branch is based on Omar's integrated Prototype 2 branch. It adds three rubric criteria:
`factual_accuracy`, `completeness`, and `evidence_grounding`.

## Rubric scoring

Select one or more rubric criteria with `reference_evidence` as a parameter. All selected
criteria weights must still total 100.00. The executor sends the approved system instructions,
prompt, response and reference evidence to a separately configured judge model
(`ASSISTANT_MODEL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`). The judge returns a JSON
score from 0 to 1, rationale, verbatim reference excerpts and evaluator model identity.
Invalid, missing, or out of range judgments leave the automatic total null. The
per criterion response and saved evaluation evidence include model, rationale and excerpts.

This implementation does not claim that an LLM judgment proves factual correctness.
The rubric score is an assessment based on the supplied reference and judge behavior.
A live API key is required for live subjective scoring; demo mode cannot fabricate a judge.

## Human review API

`POST /runs/{run_id}/reviews` accepts:
```json
{"reviewer_id":"reviewer1","rating":80,"rationale":"Clear but missing a citation"}
```
`GET /runs/{run_id}/reviews` returns every revision in chronological order.
Each review includes ID, run ID, reviewer ID, rating, rationale, revision and timestamp.
Earlier revisions are retained. Neither endpoint modifies automated run totals.
Apply Alembic revision `0005_lina_reviews` before using the review endpoints.

## Integration handoffs

Pranjal: confirm evaluator model configuration and model call contract.
Omar: confirm human review migration and transaction/locking contract.
Ahmad: use the two review endpoints and display human ratings separately.
Before shared deployment, reviewer identity must be bound to authenticated users
rather than trusting a client supplied reviewer ID. Live model and PostgreSQL
integration tests are still required in the deployed environment.
