# Contributing

This repository is maintained by the USF senior capstone team working on the Microsoft LLM Testing Harness project.

## Branching

Do not develop significant features directly on `main`.

Create a short-lived branch for each focused unit of work. Recommended naming patterns:

- `feature/<short-description>`
- `fix/<short-description>`
- `docs/<short-description>`
- `spike/<short-description>` for exploratory technical work

Examples:

- `feature/model-endpoints`
- `feature/test-schema`
- `feature/results-dashboard`
- `docs/kickoff-notes`

## Pull Requests

For significant changes:

1. Create or reference the related GitHub Issue when practical.
2. Work on a feature branch.
3. Open a pull request into `main`.
4. Summarize what changed and how it was tested.
5. Request review from at least one teammate when practical.
6. Resolve major review comments before merging.

Keep pull requests focused. A smaller PR that does one thing well is easier to review and debug than a giant mixed change.

## Commits

Use concise commit messages that describe the change, for example:

- `Add initial test schema`
- `Implement endpoint configuration model`
- `Document kickoff requirements`
- `Fix scoring weight calculation`

## Issues

Use GitHub Issues to track concrete implementation tasks, research questions, bugs, and blockers.

A useful issue should state:

- what needs to be accomplished;
- why it matters;
- what counts as done;
- known dependencies or open questions.

## Shared Engineering Expectations

- Do not commit secrets or credentials.
- Keep documentation updated when architecture or requirements change.
- Avoid making major architectural decisions in isolation.
- Prefer incremental working integrations over large disconnected components.
- Test changes before requesting review.
- Raise blockers early during team or Microsoft mentor meetings.

## Architecture Decisions

Major decisions that affect multiple workstreams should be documented in `docs/decisions/` using a short Architecture Decision Record (ADR). Examples include choosing the backend framework, database strategy, evaluator architecture, or Azure deployment approach.
