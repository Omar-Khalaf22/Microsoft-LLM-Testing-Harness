# Preliminary Data Model

> **Status:** Preliminary / subject to change. This model is intended to give the team a shared starting point for the Week 5 prototype. It is based on the current capstone requirements and should be refined as implementation decisions are confirmed with the Microsoft mentor.

## Goal

The purpose of this model is to define the main information the harness needs to remember and how those pieces relate to one another. In particular, it connects test creation and versioning to model execution, saved responses, automated scoring, human scoring, and endpoint/model configuration.

## ER Diagram

```mermaid
erDiagram
    TEST ||--o{ TEST_VERSION : has
    TEST_SUITE ||--o{ TEST_SUITE_ITEM : contains
    TEST_VERSION ||--o{ TEST_SUITE_ITEM : included_in
    TEST_VERSION ||--o{ EVALUATION_CRITERION : defines

    ENDPOINT ||--o{ MODEL : serves
    TEST_VERSION ||--o{ TEST_RUN : executed_as
    MODEL ||--o{ TEST_RUN : used_by

    TEST_RUN ||--o| MODEL_RESPONSE : produces
    TEST_RUN ||--o{ OBJECTIVE_EVALUATION : generates
    TEST_RUN ||--o{ SUBJECTIVE_EVALUATION : receives

    EVALUATION_CRITERION ||--o{ OBJECTIVE_EVALUATION : scored_by
    EVALUATION_CRITERION ||--o{ SUBJECTIVE_EVALUATION : rated_by

    TEST {
        uuid test_id PK
        string name
        string description
        datetime created_at
    }

    TEST_VERSION {
        uuid version_id PK
        uuid test_id FK
        int version_number
        text prompt
        text expected_behavior
        json edge_cases
        datetime created_at
    }

    TEST_SUITE {
        uuid suite_id PK
        string name
        text description
    }

    TEST_SUITE_ITEM {
        uuid suite_item_id PK
        uuid suite_id FK
        uuid version_id FK
        int run_order
    }

    EVALUATION_CRITERION {
        uuid criterion_id PK
        uuid version_id FK
        string criterion_type
        string evaluator_type
        text description
        decimal max_score
        json config_json
    }

    ENDPOINT {
        uuid endpoint_id PK
        string name
        string base_url
        string credential_ref
        boolean is_active
    }

    MODEL {
        uuid model_id PK
        uuid endpoint_id FK
        string model_name
        string display_name
    }

    TEST_RUN {
        uuid run_id PK
        uuid version_id FK
        uuid model_id FK
        string status
        json model_parameters
        datetime started_at
        datetime completed_at
        int latency_ms
        int prompt_tokens
        int completion_tokens
        text error_message
    }

    MODEL_RESPONSE {
        uuid response_id PK
        uuid run_id FK
        text content
        json raw_response_json
    }

    OBJECTIVE_EVALUATION {
        uuid evaluation_id PK
        uuid run_id FK
        uuid criterion_id FK
        decimal score
        boolean passed
        json details_json
    }

    SUBJECTIVE_EVALUATION {
        uuid evaluation_id PK
        uuid run_id FK
        uuid criterion_id FK
        string evaluator_id
        decimal score
        text notes
        datetime evaluated_at
    }
```

## Entity Responsibilities

| Entity | Purpose |
| --- | --- |
| `TEST` | Represents the overall test created in the harness. |
| `TEST_VERSION` | Stores a specific version of a test's prompt, expected behavior, and edge cases so previous runs remain reproducible. |
| `TEST_SUITE` | Represents a named group of tests that can be executed together. |
| `TEST_SUITE_ITEM` | Connects a test suite to specific test versions and preserves execution order. |
| `EVALUATION_CRITERION` | Defines how a test version should be evaluated, including objective or subjective criteria and any evaluator configuration. |
| `ENDPOINT` | Represents a configurable OpenAI-compatible API endpoint. The database should store a reference to credentials rather than raw secrets. |
| `MODEL` | Represents a model available through an endpoint. |
| `TEST_RUN` | Represents one execution of one test version against one model and stores run configuration, timing, usage, status, and errors. |
| `MODEL_RESPONSE` | Stores the model output and, where useful, the raw API response for the run. |
| `OBJECTIVE_EVALUATION` | Stores automatically calculated results for objective criteria. |
| `SUBJECTIVE_EVALUATION` | Stores human-entered ratings and notes for subjective criteria. |

## Example Test-Run Lifecycle

A single run would move through the model roughly like this:

```text
TEST
  ↓
TEST_VERSION
  ├── prompt
  ├── expected behavior
  └── evaluation criteria
        ↓
TEST_RUN ───── MODEL ───── ENDPOINT
  ↓
MODEL_RESPONSE
  ↓
OBJECTIVE_EVALUATION
  +
SUBJECTIVE_EVALUATION
```

Example:

```text
Test: "Logic Reasoning Test"
  ↓
Version 1: "Solve the following puzzle..."
  ↓
Run against Model A through Endpoint X
  ↓
Response saved
  ↓
Objective criteria scored automatically
  ↓
Optional human ratings/notes saved
```

## Prototype-Relevant Data Flow

For the first mini prototype, the minimum useful path is:

```text
Test Version
    ↓
Test Run
    ↓
Model Response
    ↓
Structured JSON Result
    ↓
PostgreSQL
```

The objective/subjective evaluation tables can then be connected as scoring functionality is added.

## Current Assumptions / Open Questions

This diagram intentionally does **not** settle every design decision. The following should be confirmed as the project evolves:

- Whether PostgreSQL will be the application's primary persistence layer or mainly the destination for imported JSON results.
- Whether test suites should point to exact test versions, as shown here, or automatically use a test's latest version.
- Whether objective and subjective results should remain separate tables or eventually share a generalized evaluation-result structure.
- Which evaluator types will be supported and what belongs in `config_json`.
- Whether authentication/users need to become first-class database entities.
- How Azure-managed secrets or another secret store will map to `credential_ref`.
- Which run metadata fields are guaranteed across all OpenAI-compatible endpoints.
