"""OpenAI provider: one Chat Completions call with a strict JSON-schema response format."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.services.llm.provider import LLMError

logger = logging.getLogger(__name__)


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, *, timeout: float = 60.0, client: Optional[Any] = None) -> None:
        self.model = model
        self._timeout = timeout
        self._client = client

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError as exc:  # optional dependency
                raise LLMError("The 'openai' package is not installed (pip install -r requirements.txt).") from exc
            self._client = openai.OpenAI(timeout=self._timeout, max_retries=2)  # key from OPENAI_API_KEY
        return self._client

    def generate_json(self, *, system: str, user: str, schema: dict, max_tokens: int) -> str:
        import openai

        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "resume_rewrite", "schema": schema, "strict": True}},
                max_completion_tokens=max_tokens,
            )
        except openai.AuthenticationError as exc:
            raise LLMError("OpenAI rejected the API key. Check OPENAI_API_KEY.") from exc
        except openai.BadRequestError as exc:
            raise LLMError(f"OpenAI rejected the request: {exc.message}") from exc
        except openai.RateLimitError as exc:
            raise LLMError("OpenAI rate limit reached. Try again shortly.", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"OpenAI API error ({exc.status_code}). Try again later.",
                           retryable=exc.status_code >= 500) from exc
        except openai.APIConnectionError as exc:  # includes timeouts
            raise LLMError("Could not reach the OpenAI API (network or timeout).", retryable=True) from exc

        choice = response.choices[0]
        logger.info("event=llm_call provider=openai model=%s finish_reason=%s", self.model, choice.finish_reason)
        if getattr(choice.message, "refusal", None):
            raise LLMError("The model declined this request. The draft keeps your original wording.")
        if choice.finish_reason == "length":
            raise LLMError("The model's answer was cut off (too long). Try fewer bullets or the 1-page target.")
        if not choice.message.content:
            raise LLMError("The model returned no text.")
        return choice.message.content
