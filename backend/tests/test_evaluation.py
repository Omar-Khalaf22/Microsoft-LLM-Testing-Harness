import tempfile
import unittest
from pathlib import Path

from app.evaluation.executor import TestExecutor
from app.evaluation.models import TestRequest, ValidationError
from app.evaluation.providers import DemoProvider
from app.evaluation.repository import JsonResultRepository
from app.evaluation.scoring import score_response


class EvaluationTests(unittest.TestCase):
    def test_request_validation(self) -> None:
        request = TestRequest.from_dict({"prompt": "Hello", "expected_keywords": "one, two"})
        self.assertEqual(request.expected_keywords, ["one", "two"])
        with self.assertRaises(ValidationError):
            TestRequest.from_dict({"prompt": ""})

    def test_scoring(self) -> None:
        score, criteria = score_response(
            "Explain JSON testing metadata",
            "JSON testing metadata is structured. It preserves useful test details.",
            ["JSON", "testing"],
            10,
            2,
            ["failure"],
        )
        self.assertEqual(score, 100)
        self.assertTrue(all(item.passed for item in criteria))

    def test_forbidden_term_reduces_score(self) -> None:
        score, criteria = score_response(
            "Explain JSON testing",
            "JSON testing found a dangerous error. The result is structured.",
            ["JSON", "testing"],
            10,
            2,
            ["error"],
        )
        self.assertEqual(score, 90)
        forbidden_result = next(item for item in criteria if item.name == "Forbidden terms")
        self.assertFalse(forbidden_result.passed)

    def test_end_to_end_execution_and_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonResultRepository(Path(directory) / "results.jsonl")
            executor = TestExecutor(DemoProvider(), repository)
            request = TestRequest.from_dict({"prompt": "Explain an API", "minimum_length": 20})
            result = executor.execute(request)
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.provider, "local_demo")
            self.assertEqual(len(repository.recent()), 1)

    def test_demo_models_return_different_responses(self) -> None:
        provider = DemoProvider()
        prompt = "Explain secure LLM testing"
        strong = provider.generate(prompt, "demo-strong-v1", 0.2).text
        partial = provider.generate(prompt, "demo-partial-v1", 0.2).text
        failing = provider.generate(prompt, "demo-failing-v1", 0.2).text
        self.assertEqual(len({strong, partial, failing}), 3)


if __name__ == "__main__":
    unittest.main()
