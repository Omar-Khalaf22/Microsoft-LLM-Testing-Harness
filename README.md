# Microsoft LLM Testing Harness

USF Senior Capstone project with Microsoft for Fall 2026.

## Project Overview

This project will design, build, and deploy an extensible web-based testing harness for large language models (LLMs). The application is intended to support repeatable tests and test suites against configurable OpenAI-compatible model endpoints, capture run results and metadata, support objective and subjective evaluation, and provide an interface for reviewing and comparing model performance.

The project is based in part on concepts from Brad Lawrence's existing `ai-server` evaluation workflow:
https://github.com/bradrlaw/ai-server

## Core Required Capabilities

- Create, refine, version, store, and execute tests.
- Use an LLM to assist with developing prompts, expected behaviors, edge cases, and evaluation criteria while preserving human review and approval.
- Execute individual tests or suites against configurable OpenAI-compatible endpoints and models.
- Automatically calculate objective scores where practical.
- Support subjective human ratings and evaluator notes when objective scoring is insufficient.
- Capture prompts, model responses, configuration, timestamps, latency/usage data when available, scores, evaluator input, and errors in structured JSON.
- Provide a documented method to import/load JSON results into PostgreSQL.
- Provide an HTML-based interface for managing tests, starting runs, reviewing results, entering subjective scores, and comparing models.
- Deploy the completed application to Microsoft Azure while staying within the provided resource budget.
- Provide deployment automation and project documentation.

## Project Status

**Phase:** Discovery / architecture planning

The team is currently validating requirements with the Microsoft mentor, studying the existing `ai-server/evals` workflow, defining the initial architecture, and assigning primary technical ownership areas.

Technology choices in this repository should be treated as **TBD until the team agrees on the stack and confirms any relevant preferences with the Microsoft mentor**.

## Proposed Team Workstreams

1. **Backend & LLM Integration** — model endpoints, test execution, backend APIs, run metadata, error handling.
2. **Evaluation & Test Framework** — test/rubric structure, objective scoring, subjective scoring, test versioning, AI-assisted test creation.
3. **Frontend & UX** — test management, run configuration, results/history, model comparison, human scoring interface.
4. **Cloud, Database & DevOps** — PostgreSQL/data model, JSON import/load workflow, Azure deployment, secrets/configuration, deployment automation.

These are primary ownership areas, not silos. Architecture, requirements, reviews, documentation, integration, and final testing are shared responsibilities.

## Repository Structure

```text
.
├── backend/            # Backend APIs, model execution, scoring integration
├── frontend/           # Web application / user interface
├── database/           # PostgreSQL schema, migrations, import/load utilities
├── deployment/         # Azure deployment and automation
├── examples/           # Representative LLM tests and scoring rubrics
├── tests/              # Automated tests for this application
├── docs/
│   ├── architecture.md
│   ├── requirements.md
│   ├── decisions/
│   └── meeting-notes/
├── .env.example
├── .gitignore
└── CONTRIBUTING.md
```

## Team Workflow

- `main` should remain stable.
- Development work should happen on short-lived feature branches.
- Suggested branch names include `feature/model-endpoints`, `feature/test-schema`, `feature/results-dashboard`, and `feature/postgres-schema`.
- Open a pull request before merging significant changes into `main`.
- At least one teammate should review a pull request when practical.
- Track implementation work and blockers with GitHub Issues.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the working conventions.

## Documentation

- [Requirements](docs/requirements.md)
- [Preliminary Architecture](docs/architecture.md)
- [Architecture Decision Records](docs/decisions/README.md)
- [Meeting Notes](docs/meeting-notes/README.md)

## Security Note

Never commit API keys, passwords, database credentials, Azure secrets, or other sensitive values. Use environment variables or approved secret-management mechanisms. `.env` files are intentionally excluded from version control.
