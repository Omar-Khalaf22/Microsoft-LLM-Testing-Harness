"""Model provider adapters used by the machine evaluation executor."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.assistant.prompts import DEFAULT_SYSTEM_PROMPT
from app.evaluation.demo_rubrics import demo_answer, demo_interpretation, demo_judgment
from app.evaluation.interpretation import PREVIEW_INSTRUCTIONS

MAX_PROVIDER_BODY_BYTES = 2_000_000


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str
    usage: dict[str, int | None]
    model_reported: bool = True


class DemoProvider:
    """Deterministic local provider for demonstrations without credentials."""

    name = "local_demo"

    def generate(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> ProviderResponse:
        words = re.findall(r"[A-Za-z0-9']+", prompt)
        topic = " ".join(words[:8]) if words else "the requested topic"
        scripted = demo_answer(model)
        if system_prompt == PREVIEW_INSTRUCTIONS:
            text = json.dumps(demo_interpretation(json.loads(prompt)["task_prompt"]))
        elif scripted is not None:
            text = scripted
        elif model == "demo-partial-v1":
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
        elif model == "demo-json-v1":
            text = '{"count": 3, "ok": true, "summary": "JSON testing"}'
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
            usage={"input_tokens": None, "output_tokens": None},
        )


class DemoJudgeProvider:
    name = "local_demo_judge"

    def generate(self, prompt, model, temperature, system_prompt):
        return ProviderResponse(json.dumps(demo_judgment(json.loads(prompt))), model, {})


class OpenAICompatibleProvider:
    """Adapter for an OpenAI compatible chat completions endpoint."""

    name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str):
        if not api_key:
            raise RuntimeError("An API key is required for the OpenAI compatible provider.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> ProviderResponse:
        payload = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                **({"temperature": temperature} if temperature is not None else {}),
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
                raw = response.read(MAX_PROVIDER_BODY_BYTES + 1)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Model request failed: {exc}") from exc
        if len(raw) > MAX_PROVIDER_BODY_BYTES:
            raise ValueError("Model response exceeds the supported size.")
        body = json.loads(raw)

        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}

        def reported(name):
            value = usage.get(name)
            if type(value) is int and value >= 0:
                return value
            if isinstance(value, str) and value.isascii() and value.isdecimal():
                return int(value)
            return None

        return ProviderResponse(
            text=body["choices"][0]["message"]["content"],
            model=body.get("model", model),
            model_reported=isinstance(body.get("model"), str) and bool(body["model"].strip()),
            usage={
                "input_tokens": reported("prompt_tokens"),
                "output_tokens": reported("completion_tokens"),
            },
        )
