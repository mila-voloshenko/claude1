from __future__ import annotations

from anthropic import Anthropic


class LLMConfigError(Exception):
    pass


class LLMClient:
    """Thin wrapper around the Anthropic SDK with our chosen defaults."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-7") -> None:
        if not api_key:
            raise LLMConfigError(
                "Anthropic API key is not configured. "
                "Set MAIL_ASSISTANT_ANTHROPIC_API_KEY in your .env file."
            )
        self._client = Anthropic(api_key=api_key)
        self._model = model

    @property
    def client(self) -> Anthropic:
        return self._client

    @property
    def model(self) -> str:
        return self._model
