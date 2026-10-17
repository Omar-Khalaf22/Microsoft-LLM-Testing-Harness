# Requirements and roadmap

This overview is aligned with **SRS v2.0**, revised by Omar Khalaf in October 2026 after instructor and sponsor feedback. The SRS describes the intended final application. Feature availability is documented separately in the [prototype guide](prototype-guide.md).

## Problem and intended users

Choosing an LLM depends on the task, expected output, prompt, model settings, infrastructure, and cost. A broad benchmark cannot show whether a model will satisfy a particular user's prompt. The harness is intended to preserve comparable task-specific evidence so individuals and teams can assess output quality alongside token usage and other operating measurements.

Microsoft solution architects are the capstone's initial audience, including both customer workloads and architects' own discovery, solution-design, planning, documentation, and review tasks. The configurable test approach is intended to support broader individual and enterprise use.

## Final application capabilities

| Area | Required behavior |
| --- | --- |
| Tests and suites | Create named tests, preserve exact versions, and snapshot ordered suite membership for execution. |
| Supported criteria | Select executable evaluator definitions and bind task-specific instructions, parameters, and evidence expectations. |
| LLM assistance | Suggest criteria and point allocations, with user acceptance/editing/rejection before publication. |
| Weighting | Require selected objective criterion maxima to total exactly 100 points. |
| Interpretation preview | Show the model's reported understanding before the scored request; isolate preview content from the actual test. |
| Execution | Run approved OpenAI-compatible local/cloud endpoints with recorded model settings and distinct run IDs. |
| Evidence | Retain output, state/errors, timestamps, elapsed time, and endpoint-supplied token usage. Unknown usage is not measured zero. |
| Automated evaluation | Return bounded numerical points and rationale for each selected criterion. Do not invent a complete total when a criterion evaluation is invalid or missing. |
| Saved history | Persist the run snapshot, retrieve earlier evidence, and exchange structured results. |
| Comparison/regression | Compare recorded conditions and outcomes; reruns create new evidence rather than replacing history. |
| Human review | Preserve subjective ratings, notes, reviewer provenance, and timestamps separately from automated totals. |
| Delivery | Provide the browser/API/database workflow, Azure deployment, and operating/user documentation. |

Numerical model-based rubric scores remain evaluator judgments. They are not proof of factual correctness. The final design does not carry forward the prototype's overall pass/fail threshold.

## Current development focus

- Map a reusable criteria catalog to executable evaluator methods and the database/API contract.
- Extend the fixed prototype scoring inputs into parameterized definitions with user-selected points.
- Integrate assisted criteria creation while preserving explicit user control.
- Continue detailed-design documentation, workflow integration, and traceable verification.

The current prototype already provides execution/scoring components and PostgreSQL-backed run/history work on the integration branch. The expanded catalog, complete suite/comparison workflows, human ratings, and cloud delivery remain ongoing or planned; this roadmap is not a claim that they are implemented.

## Quality and operating requirements

SRS v2.0 covers authentication and server authorization, credential/transport protection, input limits, isolation of untrusted text, approved endpoint controls, restrained operational logging, accessible controls, recorded failures, and traceable acceptance tests. Performance and catalog-growth targets require validation in the agreed deployment environment.

Open operating decisions include the approved model/assistant configuration, Azure service selection, endpoint connectivity for private local models, retention policy, and sponsor validation of proposed engineering targets.

## Documentation

- [System architecture](architecture.md)
- [Implemented ER model and planned criteria contract](data-model.md)
- [Prototype setup, verification, and limitations](prototype-guide.md)

Architecture and ER documentation have been authored, and the SRS v2.0 revision is complete. The Detailed Design Document and the expanded criteria implementation continue with the team.
