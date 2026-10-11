"""Sprint 1.2 — LLM provider abstraction: stub determinism + factory + openai compat."""
import httpx
import pytest

from app.ai.providers import (
    GenerateRequest,
    OpenAICompatibleProvider,
    PersonaHint,
    ProviderError,
    StubProvider,
    get_provider,
)

HANK_PERSONA = PersonaHint(
    name="Hank",
    interests=["farming", "trucks"],
    humor_style="dry, deadpan",
    voice_style="plain-spoken",
)
ALEX_PERSONA = PersonaHint(
    name="Alex.exe",
    interests=["AI", "automation"],
    humor_style="absurd corporate-techno-optimism",
    voice_style="rapid, buzzword-dense",
)
REQ = GenerateRequest(
    system_prompt="You are a fictional creator.",
    user_message="What do you think about automated tractors?",
)


def _req(persona: PersonaHint, message: str = "What do you think about automated tractors?") -> GenerateRequest:
    return GenerateRequest(
        system_prompt="system",
        user_message=message,
        persona=persona,
    )


def test_stub_is_deterministic_for_same_input():
    a = StubProvider().generate(_req(HANK_PERSONA))
    b = StubProvider().generate(_req(HANK_PERSONA))
    assert a.text == b.text
    assert a.model == "stub/deterministic-v1"


def test_stub_voices_are_meaningfully_different():
    hank = StubProvider().generate(_req(HANK_PERSONA)).text
    alex = StubProvider().generate(_req(ALEX_PERSONA)).text
    assert hank != alex
    assert "Hank" in hank and "AI" not in hank
    assert "Alex.exe" in alex and "automation" in alex
    # each voice reflects its own style
    assert "dry, deadpan" in hank and "plain-spoken" in hank
    assert "rapid, buzzword-dense" in alex


def test_factory_defaults_to_stub():
    assert isinstance(get_provider(), StubProvider)


def test_factory_selects_openai():
    assert isinstance(get_provider("openai"), OpenAICompatibleProvider)


def test_factory_rejects_unknown():
    with pytest.raises(ValueError):
        get_provider("nonexistent-provider")


def _openai_client(handler) -> OpenAICompatibleProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.test/v1")
    return OpenAICompatibleProvider(api_key="test-key", client=client)


def test_openai_provider_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200, json={"model": "gpt-test", "choices": [{"message": {"content": "Alex.exe here."}}]}
        )

    provider = _openai_client(handler)
    res = provider.generate(REQ)
    assert res.text == "Alex.exe here."
    assert res.model == "gpt-test"


def test_openai_provider_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(ProviderError):
        _openai_client(handler).generate(REQ)


def test_openai_provider_malformed_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    with pytest.raises(ProviderError):
        _openai_client(handler).generate(REQ)


def test_openai_provider_missing_key_raises():
    provider = OpenAICompatibleProvider(api_key="", client=httpx.Client())
    with pytest.raises(ProviderError):
        provider.generate(REQ)
