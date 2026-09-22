"""Automated machine evaluation for LLM responses."""

from .executor import TestExecutor
from .models import CriterionResult, TestRequest, TestResult, ValidationError
from .providers import DemoProvider, OpenAICompatibleProvider, ProviderResponse
from .repository import JsonResultRepository
from .scoring import score_response

__all__ = [
    "CriterionResult",
    "DemoProvider",
    "JsonResultRepository",
    "OpenAICompatibleProvider",
    "ProviderResponse",
    "TestExecutor",
    "TestRequest",
    "TestResult",
    "ValidationError",
    "score_response",
]
