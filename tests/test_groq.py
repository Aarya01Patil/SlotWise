import json
from types import SimpleNamespace
from typing import ClassVar

import pytest

from slotwise.domain import Session
from slotwise.providers import GroqProvider, live_settings, provider_failure_code


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("groq_api_key", "synthetic-groq-key")
    p = GroqProvider()
    p.close()
    return p


def test_lowercase_key_is_accepted_and_explicit_provider_wins(monkeypatch):
    monkeypatch.setenv("groq_api_key", "synthetic-groq-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert live_settings()["provider"] == "groq"
    assert live_settings()["ready"] is True
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert live_settings()["provider"] == "gemini"


def test_groq_tool_ids_and_multiturn_history_are_preserved(provider):
    captured = []
    native = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-123",
                "type": "function",
                "function": {
                    "name": "search_slots",
                    "arguments": '{"specialty":"general","date":"2026-10-09","period":"morning"}',
                },
            }
        ],
    }

    class Message:
        content = None
        tool_calls: ClassVar[list] = [
            SimpleNamespace(
                id="call-123",
                function=SimpleNamespace(
                    name="search_slots", arguments=native["tool_calls"][0]["function"]["arguments"]
                ),
            )
        ]

        def model_dump(self, **kwargs):
            return native

    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=Message())])

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    session = Session(patient_id="private-patient-id", today="2026-10-08")
    session.messages.append({"role": "patient", "text": "General tomorrow morning"})
    session.patient_turns = 1
    decision = provider.respond(session, [])
    assert decision.calls[0].name == "search_slots"
    provider.record_results(session, [("search_slots", {"ok": True, "slots": []})])
    assert session.history[-1]["tool_call_id"] == "call-123"
    session.messages.append({"role": "patient", "text": "Actually dental afternoon"})
    session.patient_turns = 2
    provider.respond(session, [])
    assert captured[-1]["messages"][-1]["content"] == "Actually dental afternoon"
    assert "private-patient-id" not in json.dumps(captured)
    assert captured[-1]["tools"][0]["function"]["name"] == "search_slots"


def test_groq_scope_is_tool_free_and_validated_locally(provider):
    captured = []

    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"category":"off_topic"}'))]
        )

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    session = Session(patient_id="private-id", today="2026-10-08")
    assert provider.classify(session, "Tell me a joke") == "off_topic"
    assert "tools" not in captured[0]
    assert "private-id" not in json.dumps(captured)
    assert session.history == []


def test_groq_http_status_is_mapped_without_exposing_error_text():
    error = SimpleNamespace(status_code=429)
    assert provider_failure_code(error) == "PROVIDER_QUOTA_EXHAUSTED"


@pytest.mark.parametrize("retry_after,expected_calls", [("2", 2), ("120", 1), ("", 1)])
def test_only_short_explicit_rate_limit_is_retried(
    provider, monkeypatch, retry_after, expected_calls
):
    import httpx
    from groq import RateLimitError

    calls, waits = [], []
    monkeypatch.setattr("slotwise.providers.time.sleep", waits.append)
    response = httpx.Response(
        429,
        headers={"retry-after": retry_after},
        request=httpx.Request("POST", "https://api.groq.com"),
    )

    def create(**kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise RateLimitError("synthetic quota", response=response, body=None)
        return "ok"

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    if expected_calls == 2:
        assert provider.complete(messages=[]) == "ok"
        assert waits == [2]
    else:
        with pytest.raises(RateLimitError):
            provider.complete(messages=[])
        assert waits == []
    assert len(calls) == expected_calls
