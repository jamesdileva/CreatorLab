"""Minimal OpenAI-compatible chat provider (OpenAI + compatible endpoints)."""
import httpx

from ...core.config import settings
from .base import GenerateRequest, GenerateResponse, LLMProvider, ProviderError


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.model = model or settings.openai_model
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=30.0,
        )

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_message},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        try:
            res = self._client.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            res.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"provider request failed: {exc}") from exc
        try:
            body = res.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"malformed provider response: {exc}") from exc
        return GenerateResponse(text=content, model=body.get("model", self.model))
