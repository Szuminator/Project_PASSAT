from types import SimpleNamespace

import pytest
import httpx
import groq
from google.genai import errors

from passat.models import ChatMessage
from passat.providers.base import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from passat.providers.factory import create_provider
from passat.providers.gemini import GeminiProvider
from passat.providers.groq import GroqProvider
from passat.settings import Settings


def test_factory_selects_offline_from_configuration():
    selection = create_provider(Settings(provider="offline"))

    assert selection.provider_name == "offline"
    assert selection.is_offline


def test_groq_is_the_default_provider_and_model():
    settings = Settings()

    assert settings.provider == "groq"
    assert settings.groq_model == "qwen/qwen3.8-27b"


def test_factory_selects_gemini_when_key_is_configured():
    selection = create_provider(
        Settings(provider="gemini", gemini_api_key="not-a-real-key", gemini_model="gemini-test")
    )

    assert selection.provider_name == "Gemini"
    assert not selection.is_offline
    assert selection.provider.model == "gemini-test"


def test_factory_selects_groq_when_key_is_configured():
    selection = create_provider(
        Settings(provider="groq", groq_api_key="not-a-real-key", groq_model="qwen-test")
    )

    assert selection.provider_name == "GroqCloud"
    assert not selection.is_offline
    assert selection.provider.model == "qwen-test"


def test_factory_selects_offline_when_groq_key_is_missing():
    selection = create_provider(Settings(provider="groq", groq_api_key=""))

    assert selection.is_offline
    assert "GROQ_API_KEY" in selection.notice


def test_factory_rejects_unimplemented_provider():
    with pytest.raises(ProviderConfigurationError):
        create_provider(Settings(provider="ollama"))


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def test_gemini_maps_shared_history_and_system_instruction():
    models = FakeModels(response=SimpleNamespace(text="  Odpowiedź po polsku.  "))
    provider = GeminiProvider("not-a-real-key", "gemini-test", client=SimpleNamespace(models=models))

    reply = provider.generate_reply(
        "A teraz odpowiedz.",
        [ChatMessage("user", "Pytanie wcześniejsze"), ChatMessage("assistant", "Odpowiedź wcześniejsza")],
        "Odpowiadaj po polsku.",
    )

    assert reply == "Odpowiedź po polsku."
    assert models.kwargs["model"] == "gemini-test"
    assert [item.role for item in models.kwargs["contents"]] == ["user", "model", "user"]
    assert models.kwargs["contents"][-1].parts[0].text == "A teraz odpowiedz."
    assert models.kwargs["config"].system_instruction == "Odpowiadaj po polsku."
    assert models.kwargs["config"].thinking_config.thinking_level.name == "LOW"


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (429, ProviderRateLimitError),
        (404, ProviderUnavailableError),
        (503, ProviderUnavailableError),
    ],
)
def test_gemini_maps_auth_and_quota_errors_without_leaking_api_body(status_code, exception_type):
    models = FakeModels(error=errors.APIError(status_code, {"error": {"message": "sensitive response"}}))
    provider = GeminiProvider("not-a-real-key", "gemini-test", client=SimpleNamespace(models=models))

    with pytest.raises(exception_type) as raised:
        provider.generate_reply("test", [], "system")

    assert "sensitive response" not in str(raised.value)
    assert "not-a-real-key" not in str(raised.value)

    if status_code == 503:
        assert "przeciążone lub niedostępne" in str(raised.value)


def test_gemini_rejects_blank_key_before_request():
    with pytest.raises(ProviderAuthenticationError):
        GeminiProvider("  ", "gemini-test", client=SimpleNamespace())


def test_gemini_maps_network_error_to_safe_message():
    models = FakeModels(error=httpx.ConnectError("network detail with key-like content"))
    provider = GeminiProvider("not-a-real-key", "gemini-test", client=SimpleNamespace(models=models))

    with pytest.raises(ProviderUnavailableError, match="połączyć z Gemini") as raised:
        provider.generate_reply("test", [], "system")

    assert "key-like content" not in str(raised.value)


class FakeGroqCompletions:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def fake_groq_client(*results):
    completions = FakeGroqCompletions(*results)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_groq_sends_system_instruction_and_conversation_history():
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="  Odpowiedź po polsku.  "))]
    )
    client, completions = fake_groq_client(completion)
    provider = GroqProvider("not-a-real-key", "qwen-test", client=client)

    reply = provider.generate_reply(
        "Kto?",
        [ChatMessage("user", "Pytanie wcześniejsze"), ChatMessage("assistant", "Kontekst")],
        "Odpowiadaj po polsku.",
    )

    request = completions.calls[0]
    assert reply == "Odpowiedź po polsku."
    assert request["model"] == "qwen-test"
    assert [item["role"] for item in request["messages"]] == [
        "system", "user", "assistant", "user"
    ]
    assert request["messages"][0]["content"] == "Odpowiadaj po polsku."
    assert request["messages"][-1]["content"] == "Kto?"
    assert request["max_completion_tokens"] == 1024
    assert request["reasoning_effort"] == "none"


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (404, ProviderUnavailableError),
        (500, ProviderUnavailableError),
    ],
)
def test_groq_maps_api_errors_without_exposing_response_body(status_code, exception_type):
    response = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    if status_code == 500:
        error = groq.InternalServerError("sensitive response", response=response, body={})
    elif status_code == 401:
        error = groq.AuthenticationError("sensitive response", response=response, body={})
    elif status_code == 403:
        error = groq.PermissionDeniedError("sensitive response", response=response, body={})
    else:
        error = groq.NotFoundError("sensitive response", response=response, body={})
    client, _ = fake_groq_client(error)
    provider = GroqProvider("not-a-real-key", "qwen-test", client=client)

    with pytest.raises(exception_type) as raised:
        provider.generate_reply("test", [], "system")

    assert "sensitive response" not in str(raised.value)
    assert "not-a-real-key" not in str(raised.value)


def test_groq_handles_429_retry_after_with_one_bounded_retry(monkeypatch):
    response = httpx.Response(
        429,
        headers={"retry-after": "2"},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    error = groq.RateLimitError("sensitive response", response=response, body={})
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Po przerwie."))]
    )
    client, completions = fake_groq_client(error, completion)
    provider = GroqProvider("not-a-real-key", "qwen-test", client=client)
    waits = []
    monkeypatch.setattr("passat.providers.groq.time.sleep", waits.append)

    assert provider.generate_reply("test", [], "system") == "Po przerwie."
    assert len(completions.calls) == 2
    assert waits == [2.0]


def test_groq_does_not_retry_when_retry_after_exceeds_safe_wait(monkeypatch):
    response = httpx.Response(
        429,
        headers={"retry-after": "600"},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    error = groq.RateLimitError("sensitive response", response=response, body={})
    client, completions = fake_groq_client(error)
    provider = GroqProvider("not-a-real-key", "qwen-test", client=client)
    monkeypatch.setattr("passat.providers.groq.time.sleep", lambda _: pytest.fail("unexpected wait"))

    with pytest.raises(ProviderRateLimitError, match="600 s"):
        provider.generate_reply("test", [], "system")

    assert len(completions.calls) == 1


def test_groq_rejects_blank_key_before_request():
    with pytest.raises(ProviderAuthenticationError, match="GROQ_API_KEY"):
        GroqProvider("  ", "qwen-test")
