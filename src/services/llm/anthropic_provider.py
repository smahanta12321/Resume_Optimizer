"""Anthropic (Claude) provider: one Messages API call with a JSON-schema output format."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.services.llm.provider import LLMError

logger = logging.getLogger(__name__)

# Models that accept server-side refusal fallbacks ("default" routing picks the fallback model).
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, *, timeout: float = 60.0, client: Optional[Any] = None) -> None:
        self.model = model
        self._timeout = timeout
        self._client = client

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # optional dependency
                raise LLMError("The 'anthropic' package is not installed (pip install -r requirements.txt).") from exc
            # Credentials resolve from the environment (ANTHROPIC_API_KEY, token, or saved profile).
            self._client = anthropic.Anthropic(timeout=self._timeout, max_retries=2)
        return self._client

    def generate_json(self, *, system: str, user: str, schema: dict, max_tokens: int) -> str:
        import anthropic

        client = self._get_client()
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "medium"},
        )
        if self.model in _FALLBACK_MODELS:
            kwargs.update(betas=[_FALLBACK_BETA], fallbacks="default")
        try:
            response = (client.beta.messages.create(**kwargs) if "betas" in kwargs
                        else client.messages.create(**kwargs))
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("The Anthropic API key lacks permission for this model.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Anthropic model {self.model!r} was not found. Check RESUME_OPTIMIZER_LLM_MODEL.") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Anthropic rejected the request: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached. Try again shortly.", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error ({exc.status_code}). Try again later.",
                           retryable=exc.status_code >= 500) from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise LLMError("Could not reach the Anthropic API (network or timeout).", retryable=True) from exc

        logger.info("event=llm_call provider=anthropic model=%s stop_reason=%s request_id=%s",
                    self.model, response.stop_reason, getattr(response, "_request_id", ""))
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request. The draft keeps your original wording.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model's answer was cut off (too long). Try fewer bullets or the 1-page target.")
        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            raise LLMError("The model returned no text.")
        return text
