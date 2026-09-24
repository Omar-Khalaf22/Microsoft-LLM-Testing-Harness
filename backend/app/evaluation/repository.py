"""Persistent JSON result storage for evaluation runs."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from .models import TestResult


class ResultRepository(Protocol):
    def save(
        self,
        result: TestResult,
        *,
        test_id: str | None = None,
        test_name: str | None = None,
        test_version: int | None = None,
    ) -> TestResult | None: ...

    def recent(self, limit: int = 10) -> list[dict[str, Any]]: ...


class JsonResultRepository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()

    def save(
        self,
        result: TestResult,
        *,
        test_id: str | None = None,
        test_name: str | None = None,
        test_version: int | None = None,
    ) -> None:
        with self.lock, self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.lock, self.path.open("r", encoding="utf-8") as file:
            rows = [json.loads(line) for line in file if line.strip()]
        return list(reversed(rows[-limit:]))
