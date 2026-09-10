# Preliminary Architecture

> Status: exploratory. This document is intentionally unconfirmed until the team confirms requirements and selects the implementation stack.

## High-Level Flow

```text
User
  ↓
Web Interface
  ↓
Backend / Application API
  ↓
Test Execution Service
  ↓
OpenAI-Compatible Endpoint(s)
  ↓
Model Response
  ↓
Evaluation Pipeline
  ├── Objective scoring
  └── Subjective human scoring
  ↓
Structured Run Result
  ├── JSON representation/export
  └── Persistent storage / PostgreSQL workflow
  ↓
History + Model Comparison UI
```

## Major Components

### 1. Frontend

Responsibilities:
- manage tests and test versions;
- configure test runs;
- select endpoints/models;
- start individual tests or suites;
- review model outputs and metadata;
- enter subjective ratings/notes;
- compare historical runs and models.

### 2. Backend / Application API

Responsibilities:
- expose application operations to the frontend;
- validate test/run configuration;
- coordinate endpoint/model requests;
- capture responses, errors, timing, and usage metadata;
- pass responses to the evaluation system;
- persist/retrieve application state.

### 3. Test & Evaluation Framework

Responsibilities:
- represent prompts, expected behaviors, edge cases, and evaluation criteria;
- support test versioning;
- define reusable objective evaluator types where practical;
- calculate objective scores;
- support human subjective scoring;
- integrate LLM-assisted test/rubric development with human approval.

A key design question is how to generalize Brad Lawrence's current per-test `check.py` approach for tests created through the web interface.

### 4. Data / PostgreSQL

Potential entities include:
- Test
- TestVersion
- TestSuite
- Endpoint
- Model
- TestRun
- ModelResponse
- ObjectiveEvaluation
- SubjectiveEvaluation
- RunMetadata

The final schema is TBD. The project also requires structured JSON run results and a documented JSON-to-PostgreSQL load/import process.

### 5. Azure / Deployment

Responsibilities:
- host the completed application in Microsoft Azure;
- protect credentials/secrets;
- support repeatable deployment automation;
- remain within the provided Azure budget;
- document deployment and operating procedures.

## Reference Workflow

Brad Lawrence's current `ai-server/evals` system provides an important reference implementation:

```text
prompt.txt
  ↓
eval-run.py
  ↓
OpenAI-compatible model endpoint
  ↓
raw output + metadata
  ↓
test-specific check.py
  +
human scores.json
  ↓
generated summary / comparison views
```

The capstone may evolve this workflow into a generalized, persistent, web-based application. The exact reuse/reimplementation boundary should be confirmed with the Microsoft mentor.

## Architecture Decisions Still Needed

- frontend framework;
- backend language/framework;
- persistence architecture;
- evaluator/plugin design;
- asynchronous vs synchronous run execution;
- API key/secret storage;
- Azure service selection;
- deployment automation approach;
- authentication/authorization requirements;
- supported model endpoint configuration model.
