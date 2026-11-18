"""Resolve request profile IDs from trusted server configuration."""

from hashlib import sha256
from urllib.parse import urlsplit

from app.config import Settings, TargetProfile
from app.evaluation.providers import DemoJudgeProvider, DemoProvider, OpenAICompatibleProvider
from app.storage.errors import Conflict, NotFound
from app.storage.records import ProfileSelection

DEMO_MODELS = (
    "demo-outlook-a",
    "demo-outlook-b",
    "demo-mining-a",
    "demo-mining-b",
    "demo-mining-missing",
    "demo-mining-duplicate",
    "demo-json-v1",
    "demo-strong-v1",
)
OPENAI_MODELS = ("gpt-4.1-mini", "gpt-5.4-mini", "gpt-5.4")


def profiles(settings: Settings) -> dict[str, ProfileSelection]:
    mode = settings.llm_provider.strip().lower()
    targets = settings.target_profiles
    if mode == "demo":
        provider, endpoint_id = DemoProvider.name, "in-process-demo"
        targets = targets or [
            TargetProfile(profile_id=m, model=m, temperature=0.2) for m in DEMO_MODELS
        ]
    elif mode == "openai" and _approved_openai(settings):
        provider = OpenAICompatibleProvider.name
        base_url = settings.openai_base_url.rstrip("/")
        fingerprint = sha256(base_url.encode()).hexdigest()[:24]
        endpoint_id = "openai-" + fingerprint
        if not targets and base_url == "https://api.openai.com/v1":
            targets = [TargetProfile(profile_id=m, model=m, temperature=0.2) for m in OPENAI_MODELS]
    else:
        return {}
    return {
        p.profile_id: ProfileSelection(
            profile_id=p.profile_id,
            profile_revision=p.profile_revision,
            provider=provider,
            endpoint_id=endpoint_id,
            requested_model=p.model,
            parameter_schema={
                "type": "object",
                "properties": {"temperature": {"type": "number", "minimum": 0, "maximum": 2}}
                if p.temperature is not None
                else {},
                "additionalProperties": False,
            },
            parameters={"temperature": p.temperature} if p.temperature is not None else {},
        )
        for p in targets
    }


def resolve_profile(settings: Settings, profile_id: str) -> ProfileSelection:
    profile = profiles(settings).get(profile_id)
    if profile is None:
        raise NotFound("The approved model profile is unavailable.")
    return profile


def resolve_archived(settings: Settings, archived: ProfileSelection) -> ProfileSelection:
    try:
        current = resolve_profile(settings, archived.profile_id)
    except NotFound:
        raise Conflict("The saved profile is unavailable. Choose an approved profile.") from None
    if current != archived:
        raise Conflict("The saved profile changed. Choose an approved profile.")
    return current


def target_provider(settings: Settings, selection: ProfileSelection):
    if selection.provider == DemoProvider.name:
        return DemoProvider()
    return _openai_provider(settings)


def judge_context(settings: Settings) -> dict:
    if settings.llm_provider.strip().lower() == "demo":
        return {
            "judge_provider": DemoJudgeProvider(),
            "judge_model": "demo-rubric-judge-v1",
            "judge_profile_id": "local-demo-judge",
            "judge_profile_revision": 1,
        }
    return {
        "judge_provider": (
            _openai_provider(settings)
            if settings.judge_model and _approved_openai(settings)
            else None
        ),
        "judge_model": settings.judge_model or None,
        "judge_profile_id": settings.judge_profile_id or None,
        "judge_profile_revision": settings.judge_profile_revision if settings.judge_model else None,
    }


def _approved_openai(settings):
    endpoint = urlsplit(settings.openai_base_url)
    return (
        settings.openai_base_url in settings.approved_model_endpoints
        and endpoint.scheme in ("http", "https")
        and bool(endpoint.hostname)
        and not (endpoint.username or endpoint.password or endpoint.query or endpoint.fragment)
        and bool(settings.openai_api_key.get_secret_value().strip())
    )


def _openai_provider(settings):
    return OpenAICompatibleProvider(
        api_key=settings.openai_api_key.get_secret_value().strip(),
        base_url=settings.openai_base_url,
    )
