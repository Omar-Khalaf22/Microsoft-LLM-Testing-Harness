# Prototype 2 integration for local review

This implementation starts from Lina's `prototype-2-lina` commit
`e9fafc01d6323e6c934a928552735428bf614557`. That commit includes Pranjal's
`pranjal-runs` commit `2492c38185fc12541d7d077be40099577fad7899`.
Omar's structured evaluators from `d7e7859` and the local prompt-persistence and
score-only changes are incorporated. Nothing needs to be cherry-picked from an
older download. This package contains no commits or remote branch changes.

## Implemented scope

| Proposal | Result |
| --- | --- |
| O1 | All ten structured JSON evaluators, including schema validation and their existing regression coverage |
| O2 | Versioned base/custom/effective instructions, selected criteria and parameters, point allocations, immutable run snapshots, generated recommendation provenance and approved configurations |
| O3 | `GET /evaluation/criteria` reads executable definitions from the shared registry |
| L1–L4 integration | One catalog/registry/parameter validator/dispatcher; Lina's ten content checks; corrected point arithmetic and forbidden-term semantics |
| P1–P2 completion | Existing system-level prompting preserved; fixed configurable recommendation model; `POST /assistant/suggest-criteria`; strict output validation and separate assistant instructions |
| A1 | Ten pattern/numeric evaluators with explicit numeric extraction, regex validation, bounded inputs and match timeout |
| A2 | API/executor/PostgreSQL integration coverage with mocked external calls |
| A3 | Objective and suggestion controls, editable parameters and points, include/remove/add controls, explicit approval, system instructions, scoring evidence and saved-run reopening |

The catalog contains 110 candidate definitions, of which 36 are executable:
30 proposed new checks and the six original checks. Adding definitions needed to
cover the proposal expanded Lina's approximate-100-entry candidate list. Planned
entries remain unavailable to execution, recommendations and the supported API.
Categories, required inputs, proposed methods and research references have been
corrected. Planned methods remain design candidates rather than validated scoring
algorithms. No external evaluation framework is installed or its code copied.

This implements the team's Prototype 2 proposal. Final-system capabilities such as
suite comparisons, human-rating management, interpretation-preview UI, Azure
deployment, authorization and model-based judging are outside that proposal's
implementation scope. Their DDD/SRS requirements remain future work.

## Governing decisions

The DDD and Omar's October 21 decisions govern conflicts with older wording:

- No overall pass/fail field, threshold decision or quality badge. Operational
  execution status remains distinct from the numerical quality score.
- Each selected criterion has positive maximum points with up to two decimal
  places. Allocations total exactly 100.00 before the model is called.
- Completion values are unweighted values in [0,1]. The scoring layer multiplies
  them by the allocated maximum using decimal arithmetic, rounds each earned
  value to cents using ROUND_HALF_UP, and sums those displayed earned points.
  No criterion can earn more than its maximum.
- A completed unmet condition can earn zero. A provider/evaluator failure has
  no completion value or earned points; the overall score stays null. Valid
  results from other evaluators remain inspectable.
- Binary criterion booleans are retained for compatibility; they are never used
  to classify the entire test. Human judgments do not alter automated scores.
- A technical interpretation-preview failure would not automatically prevent
  scored execution. This patch introduces no preview gate or preview feature.
- Missing token usage remains null. Demo mode also leaves token counts unknown
  rather than presenting word counts as real tokenizer measurements.
- The DDD's detailed Prototype 2 sections and proposal establish flexible criteria
  as P2 scope; the broad constraints paragraph's "later prototypes" wording is
  superseded for that scheduling question.

## One configuration contract

The selected-criteria API uses this shape:

```json
{
  "test_name": "JSON response check",
  "objective": "Return a JSON object with a numeric count",
  "prompt": "Return JSON with count equal to 3",
  "model": "demo-json-v1",
  "base_system_prompt": "Return precise JSON.",
  "custom_system_prompt": "Do not use Markdown fences.",
  "configuration_state": "approved",
  "criteria": [
    {"criterion_id": "valid_json", "parameters": {}, "weight": 60},
    {"criterion_id": "json_field_type", "parameters": {"field":"count","type":"integer"}, "weight": 40}
  ]
}
```

`criteria` and the original six-check request fields are alternative contracts.
Mixing them is rejected. Original requests containing `weights`,
`expected_keywords`, `minimum_length`, `minimum_sentences` and `forbidden_terms`
remain supported. Zero disables a check in that legacy contract; zero is not a
valid allocation for a newly selected criterion.

A recommendation request contains `objective` and `test_prompt`. The service uses
`ASSISTANT_MODEL` (default `gpt-4o-mini`), independently of the model under test.
It sends only supported registry definitions and returns validated suggestions
with `criterion_id`, `parameters`, `maximum_points` and `reason`. Unknown IDs,
planned checks, duplicate IDs, invalid parameters and bad totals reject the
entire response; they are never silently removed.

Generated recommendations are saved with status `generated`. The frontend does
not execute them until the user reviews and approves the selected configuration.
The run stores the original generated configuration and the final approved
criteria separately. Users can reject suggestions, add supported criteria, edit
parameters and reallocate points. A saved recommendation ID must refer to the
same objective and prompt. After changing those inputs, generate again or approve
a manual configuration without attaching an unrelated recommendation ID.

The assistant never evaluates model responses. Semantic/model-based evaluators
remain planned. No selected ID can introduce arbitrary Python or JavaScript.

## Storage and history

Migration `0004_prototype2` adds a recommendation table and explicit criterion ID,
status, normalized value, earned points and maximum points to evaluation rows.
Legacy evaluation values are not reinterpreted or backfilled. The old `score`
column continues to mean awarded points divided by 100 for compatibility; new
explicit columns carry the separate quantities. Error rows have nullable scores
and condition flags. Uniqueness and score-bound constraints protect new evidence.

Test-version JSONB records the approved criterion configuration and captured
system instructions; it does not require one database column per criterion.
New run snapshots retain submitted and resolved prompts, objective, catalog
revision, selected definition snapshots, model/endpoint identity, settings,
original suggestions, approval assertion timestamp and all results. Secrets are
excluded. Endpoint snapshots exclude credentials and query strings.

Changing name, user/system prompts, objective, selected criteria, parameters,
allocations or catalog revision creates a sequential version. Changing only the
model or temperature creates another run of the same version. Selecting an older
version and submitting its original configuration reuses that version.
Concurrent version creation still locks the parent test within the transaction.
Changing the global system default creates a new version when it changes the
resolved instructions. Submitted system-prompt whitespace is preserved.

Generated recommendation provenance and each run's approval timestamp do not
create a new version when the executable test definition is unchanged.

Legacy records stay unchanged. Public history projections omit old overall
pass/fail fields. Unrecorded historical system instructions, maxima and totals
stay unknown; current defaults and averaged criterion values are not substituted.
`GET /runs/{run_id}` retrieves one committed result. New snapshots reload exactly,
including evaluator failures and original versus edited configurations.

A model-provider failure is saved first, then returned as HTTP 502 with its run
ID. The browser loads that failed run so its evidence remains accessible. A
storage failure rolls back and returns a sanitized HTTP 500. Invalid requests
return 422 before model execution; absent test/version/recommendation/run IDs
return 404. Evaluator failures return a saved run with operational status
`failed`, null total and criterion evidence. Nothing converts those errors into
completed zero scores. Assistant failures return structured errors and allow an
explicit retry; there is no hidden paid retry loop.

## Evaluator boundaries

Numeric checks require the entire response, after outer whitespace trimming, to
be one signed decimal/scientific numeric scalar. They never guess which number
in prose should be measured. Ambiguous or nonnumeric text earns zero with a clear
explanation. Comparisons use decimals; ranges include both bounds and tolerance
is absolute. Numeric values outside the documented supported exponent range
(+/-1000) are noncompliant.

Regex checks use a 256-character pattern limit, 100,000-character response limit
and 50 ms matching timeout. A timeout is an incomplete evaluation. Invalid
patterns are rejected before execution. Email/URL checks verify basic syntax;
they do not fetch a URL or verify mailbox delivery. Section checks match
standalone plain/Markdown headings, ignoring case and a trailing colon. Word
counts use Unicode word tokens and preserve internal apostrophes/hyphens.

Structured checks use complete strict JSON, reject duplicate keys and nonfinite
numbers, and treat field names as literal top-level keys. JSON Schema supports
Draft 2020-12 with local fragment references only, without network retrieval.
Schema format keywords remain annotations; use the dedicated format checks for
email/URL syntax.

## Research references

These are taxonomy and design references, not claims that this harness implements
all of their capabilities. Each catalog entry links its relevant references.

- [Promptfoo assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/)
- [DeepEval metric overview](https://deepeval.com/docs/metrics-introduction)
- [Ragas metric overview](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/)
- [LangSmith evaluation approaches](https://docs.langchain.com/langsmith/evaluation-types)
- [Regex maintainer documentation](https://pypi.org/project/regex/)

The third-party frameworks' threshold conventions do not govern this tool.
