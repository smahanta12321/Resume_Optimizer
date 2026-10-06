"""LLM provider abstraction.

Providers return raw JSON text constrained to a JSON schema; callers validate
it with Pydantic. API keys are read by each SDK from the environment and are
never stored, logged, or shown by this app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

from src.config import Settings

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5"}  # OpenAI: the user must choose a model
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


class LLMError(RuntimeError):
    """A provider call failed. ``str(err)`` is user-facing and never includes secrets or content."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(self, *, system: str, user: str, schema: dict, max_tokens: int) -> str:
        """Return JSON text that should match ``schema``. Raises ``LLMError``."""
        ...


@dataclass(frozen=True)
class ProviderStatus:
    available: bool
    message: str
    provider: str = "none"
    model: str = ""


def provider_status(settings: Settings) -> ProviderStatus:
    """Whether AI rewriting can be offered, and a user-facing explanation."""
    name = settings.llm_provider
    if name in ("", "none"):
        return ProviderStatus(False, "AI rewriting is off (RESUME_OPTIMIZER_LLM_PROVIDER=none). "
                                     "Drafts use your profile wording unchanged.")
    if name not in KEY_ENV:
        return ProviderStatus(False, f"Unknown LLM provider {name!r}. Use 'anthropic', 'openai' or 'none'.")
    model = settings.llm_model or DEFAULT_MODELS.get(name, "")
    if not model:
        return ProviderStatus(False, f"Set RESUME_OPTIMIZER_LLM_MODEL to the {name} model you want to use.", name)
    if name == "openai" and not os.getenv(KEY_ENV[name]):
        return ProviderStatus(False, f"{KEY_ENV[name]} is not set in the environment.", name, model)
    if name == "anthropic" and not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
                                    or os.getenv("ANTHROPIC_PROFILE")):
        # The Anthropic SDK can also use an `ant auth login` profile, so this is a hint, not a block.
        return ProviderStatus(True, "No ANTHROPIC_API_KEY found in the environment; the SDK will try a saved "
                                    "`ant auth login` profile.", name, model)
    return ProviderStatus(True, f"AI rewriting available via {name} ({model}).", name, model)


def get_provider(settings: Settings) -> Optional[LLMProvider]:
    status = provider_status(settings)
    if not status.available:
        return None
    if status.provider == "anthropic":
        from src.services.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(status.model, timeout=settings.llm_timeout_seconds)
    from src.services.llm.openai_provider import OpenAIProvider

    return OpenAIProvider(status.model, timeout=settings.llm_timeout_seconds)
