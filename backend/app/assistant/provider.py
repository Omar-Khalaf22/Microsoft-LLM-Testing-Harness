from typing import Any, Protocol

import httpx

from app.config import Settings


class AssistantError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class RecommendationProvider(Protocol):
    async def complete(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str: ...


class OpenAIRecommendationProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        if not self.settings.openai_api_key.get_secret_value().strip():
            raise AssistantError(
                503, "assistant_unconfigured", "Assistant credentials are missing."
            )
        try:
            async with httpx.AsyncClient(timeout=self.settings.assistant_timeout_seconds) as client:
                response = await client.post(
                    f"{str(self.settings.openai_base_url).rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key.get_secret_value()}"
                    },
                    json={
                        "model": self.settings.assistant_model,
                        "messages": messages,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "criteria_recommendations",
                                "strict": False,
                                "schema": schema,
                            },
                        },
                    },
                )
                response.raise_for_status()
                choice = response.json()["choices"][0]
                if not isinstance(choice, dict):
                    raise ValueError("Invalid choice")
                message = choice["message"]
                if not isinstance(message, dict):
                    raise ValueError("Invalid message")
                if choice.get("finish_reason") != "stop" or message.get("refusal"):
                    raise ValueError("Incomplete or refused response")
                content = message["content"]
                if not isinstance(content, str):
                    raise ValueError("Missing content")
                return content
        except httpx.TimeoutException:
            raise AssistantError(504, "assistant_timeout", "Assistant request timed out.") from None
        except httpx.HTTPError:
            raise AssistantError(
                502, "assistant_provider_error", "Assistant request failed."
            ) from None
        except (KeyError, IndexError, TypeError, ValueError, RecursionError):
            raise AssistantError(
                502, "assistant_invalid_output", "Invalid assistant response."
            ) from None
