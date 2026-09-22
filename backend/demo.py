"""Entry point for the LLM Testing Harness browser demo."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.evaluation.executor import TestExecutor
from app.evaluation.models import TestRequest, ValidationError
from app.evaluation.providers import DemoProvider, OpenAICompatibleProvider
from app.evaluation.repository import JsonResultRepository

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "demo_static"
DATA_DIR = ROOT / "data"


def build_executor() -> TestExecutor:
    provider_name = os.getenv("LLM_PROVIDER", "demo").lower()
    if provider_name == "openai":
        provider = OpenAICompatibleProvider(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
    else:
        provider = DemoProvider()
    return TestExecutor(provider, JsonResultRepository(DATA_DIR / "results.jsonl"))


EXECUTOR = build_executor()


class HarnessHandler(SimpleHTTPRequestHandler):
    """Serve the demo interface and its JSON API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def _send_json(self, status: int, body: dict | list) -> None:
        encoded = json.dumps(body, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 100_000:
            raise ValidationError("Request is too large.")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            raise ValidationError("Request body must be valid JSON.") from exc
        if not isinstance(value, dict):
            raise ValidationError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {"status": "healthy", "provider": EXECUTOR.provider.name},
            )
            return
        if path == "/api/results":
            self._send_json(HTTPStatus.OK, EXECUTOR.recent_results(limit=10))
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/run":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found."})
            return
        try:
            request = TestRequest.from_dict(self._read_json())
            result = EXECUTOR.execute(request)
            self._send_json(HTTPStatus.OK, result.to_dict())
        except ValidationError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            print(f"Execution error: {exc}", file=sys.stderr)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "The test could not be completed."},
            )


def run() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), HarnessHandler)
    print(f"LLM Testing Harness is ready at http://{host}:{port}")
    print(f"Provider: {EXECUTOR.provider.name}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
