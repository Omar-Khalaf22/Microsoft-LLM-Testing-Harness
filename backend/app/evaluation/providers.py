"""Model provider adapters used by the machine evaluation executor."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str
    usage: dict[str, int]


class DemoProvider:
    """Deterministic local provider for demonstrations without credentials."""

    name = "local_demo"

    def generate(self, prompt: str, model: str, temperature: float) -> ProviderResponse:
        words = re.findall(r"[A-Za-z0-9']+", prompt)
        topic = " ".join(words[:8]) if words else "the requested topic"
        if model == "demo-partial-v1":
            text = (
                f"Partial response for: {topic}. "
                "This answer provides a short overview but leaves out several requested details "
                "and supporting concepts."
            )
        elif model == "demo-failing-v1":
            text = (
                "Error: the requested information is unavailable. "
                "The model could not complete the requested analysis."
            )
        else:
            text = (
                f"Complete analysis for: {topic}. "
                "This response addresses the requested topic with structured reasoning and "
                "relevant technical details. Key concepts include testing, JSON, metadata, "
                "security, encryption, privacy, authentication, and reliable evaluation. It "
                "explains the execution pipeline, model invocation, response validation, and "
                "result storage clearly. The result is complete and ready for automated scoring."
            )
        return ProviderResponse(
            text=text,
            model=model if model.startswith("demo-") else "demo-strong-v1",
            usage={"input_tokens": len(words), "output_tokens": len(text.split())},
        )


class OpenAICompatibleProvider:
    """Adapter for an OpenAI compatible chat completions endpoint."""

    name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str):
        if not api_key:
            raise RuntimeError(
                "An API key is required for the OpenAI compatible provider."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, model: str, temperature: float) -> ProviderResponse:
        payload = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }
        ).encode()
        request = Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Model request failed: {exc}") from exc

        usage = body.get("usage", {})
        return ProviderResponse(
            text=body["choices"][0]["message"]["content"],
            model=body.get("model", model),
            usage={
                "input_tokens": int(usage.get("prompt_tokens", 0)),
                "output_tokens": int(usage.get("completion_tokens", 0)),
            },
        )
