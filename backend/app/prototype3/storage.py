"""Boundary for Omar's forthcoming reservation helpers. No database implementation."""

from typing import Protocol

from .models import Execution, Run


class Conflict(Exception):
    pass


class Storage(Protocol):
    def reserve_test(self, test_id: str, test_version: int, rerun_of: str | None) -> Execution: ...

    def reserve_suite(self, suite_id: str) -> Execution: ...

    def execution(self, execution_id: str) -> Execution: ...

    def get(self, run_id: str) -> Run: ...

    def claim(self, run_id: str) -> Run:
        """Atomically pending -> running; return immutable snapshot or raise Conflict."""
        ...

    def checkpoint(self, run: Run) -> None:
        """Persist generated response before evaluation. Update existing row only."""
        ...

    def finish(self, run: Run) -> None:
        """Atomically persist final state; preserve identity, links and human reviews."""
        ...
