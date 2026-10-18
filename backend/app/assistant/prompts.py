"""Compose system instructions independently of the user test prompt."""

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. Follow the user's instructions accurately."


def resolve_system_prompt(
    base_system_prompt: str | None = None,
    custom_system_prompt: str | None = None,
) -> str:
    """Use the default for omitted/blank bases; append nonempty custom instructions."""
    base = (base_system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT
    custom = (custom_system_prompt or "").strip()
    if not custom:
        return base
    return f"{base}\n\nAdditional instructions:\n{custom}"
