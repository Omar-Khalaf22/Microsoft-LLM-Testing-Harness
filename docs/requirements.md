# Project Requirements

This document captures the current project requirements from the Microsoft capstone description. Implementation details and interpretations should be updated as the team confirms expectations with the Microsoft mentor.

## Required Capabilities

- Create, refine, version, store, and execute LLM tests.
- Use an LLM to assist with generating/refining prompts, expected behaviors, edge cases, and evaluation criteria while preserving human review and approval.
- Execute individual tests and test suites against configurable OpenAI-compatible endpoints and models.
- Support credentials, model parameters, and run metadata.
- Generate objective scoring criteria where practical and automatically calculate those scores after each run.
- Support subjective human evaluation when objective scoring is insufficient.
- Capture the following in structured JSON:
  - prompts;
  - model responses;
  - model/endpoint configuration;
  - timestamps;
  - latency and usage data when available;
  - automated scores;
  - evaluator input;
  - errors.
- Provide a documented method to import/load JSON results into PostgreSQL.
- Provide an HTML-based interface for:
  - managing tests;
  - reviewing prior results;
  - comparing models;
  - entering subjective scores;
  - starting new test runs.

## Deployment Constraints

- The completed application must be deployed to Microsoft Azure.
- Microsoft will provide project Azure resources/subscriptions.
- Total Azure consumption must remain below the project budget of $100/month.
- Deployment automation is an expected deliverable.

## Documentation Deliverables

The team must document:

- architecture;
- dependencies;
- security approach;
- deployment process;
- data model;
- test design;
- operating instructions;
- user instructions.

## Final Deliverables

- Azure-deployed working application.
- Source code.
- Deployment automation.
- PostgreSQL schema and JSON import/load process.
- Representative library of tests and scoring rubrics.
- Operating and user documentation.
- Final demonstration comparing multiple models or endpoints.

## Open Questions

The following items require clarification or team design decisions:

- Who is the primary intended end user?
- How much of the existing `ai-server/evals` workflow should be reused?
- How flexible should user-created tests and evaluators be?
- Should objective evaluation be limited to configurable built-in evaluator types, support custom logic, or use another approach?
- Is LLM-as-a-judge desirable or out of scope?
- Should PostgreSQL be the application's primary persistence layer or primarily an import target for JSON results?
- Which models/endpoints should be supported first?
- What Azure services and deployment automation approach should be used?
- What are the must-have MVP features versus stretch goals?
