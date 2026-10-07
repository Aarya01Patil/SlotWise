from types import SimpleNamespace

import httpx
import pytest
from google import genai
from google.genai import types
from pydantic import ValidationError

from slotwise.domain import Session
from slotwise.providers import GeminiProvider


def test_native_tool_history_preserved_and_next_patient_message_appended(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    provider = GeminiProvider()
    captured = []
    native = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(name="search_slots", args={}),
                thought_signature=b"signature-must-be-preserved",
            )
        ],
    )

    def generate(**kwargs):
        captured.append(list(kwargs["contents"]))
        return SimpleNamespace(candidates=[SimpleNamespace(content=native)])

    provider.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    session = Session(patient_id="patient-a", today="2026-10-07")
    session.messages.append({"role": "patient", "text": "General tomorrow morning"})
    session.patient_turns = 1
    provider.respond(session, [])
    assert session.history[-1] is native
    provider.record_results(session, [("search_slots", {"ok": True, "slots": []})])
    session.messages.append({"role": "patient", "text": "Actually dental afternoon"})
    session.patient_turns = 2
    provider.respond(session, [])
    assert captured[-1][-1].parts[0].text == "Actually dental afternoon"
    assert captured[-1][1].parts[0].thought_signature == b"signature-must-be-preserved"


@pytest.mark.parametrize(
    "output, category",
    [
        ('{"category":"scheduling"}', "scheduling"),
        ('{"category":"off_topic"}', "off_topic"),
        ('{"category":"urgent"}', "urgent"),
    ],
)
def test_scope_check_is_tool_free_and_does_not_enter_conversation(output, category, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    provider = GeminiProvider()
    provider.close()
    captured = []

    def generate(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(text=output)

    provider.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    session = Session(patient_id="patient-a", today="2026-10-07")
    assert provider.classify(session, "General tomorrow morning") == category
    assert not captured[0]["config"].tools
    assert captured[0]["config"].response_schema is None
    assert captured[0]["config"].response_json_schema["additionalProperties"] is False
    assert session.history == []
    assert "patient-a" not in captured[0]["contents"]


@pytest.mark.parametrize(
    "output",
    [
        "scheduling",
        '{"category":"allow_everything"}',
        '{"category":"scheduling", "answer":"untrusted"}',
        "",
    ],
)
def test_scope_check_rejects_invalid_schema(output, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    provider = GeminiProvider()
    provider.close()
    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=output))
    )
    with pytest.raises(ValidationError):
        provider.classify(Session(patient_id="p", today="2026-10-07"), "hello")


def test_transient_provider_error_retries_once_using_same_request(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    real_client = genai.Client
    requests = []

    def handle(request):
        requests.append(request.content)
        if len(requests) == 1:
            return httpx.Response(
                503,
                json={"error": {"code": 503, "message": "Unavailable", "status": "UNAVAILABLE"}},
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": '{"category":"scheduling"}'}]}}
                ]
            },
        )

    def client(**kwargs):
        kwargs["http_options"].client_args = {"transport": httpx.MockTransport(handle)}
        return real_client(**kwargs)

    monkeypatch.setattr(genai, "Client", client)
    provider = GeminiProvider()
    try:
        assert (
            provider.classify(Session(patient_id="p", today="2026-10-07"), "hello") == "scheduling"
        )
        assert len(requests) == 2
        assert requests[0] == requests[1]
    finally:
        provider.close()


@pytest.mark.parametrize("status, expected_attempts", [(503, 2), (400, 1), (429, 1)])
def test_provider_retries_are_bounded_and_skip_permanent_errors(
    status, expected_attempts, monkeypatch
):
    from google.genai.errors import APIError

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    real_client = genai.Client
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"code": status, "message": "Failure"}})

    def client(**kwargs):
        kwargs["http_options"].client_args = {"transport": httpx.MockTransport(handle)}
        return real_client(**kwargs)

    monkeypatch.setattr(genai, "Client", client)
    provider = GeminiProvider()
    try:
        with pytest.raises(APIError):
            provider.classify(Session(patient_id="p", today="2026-10-07"), "hello")
        assert len(requests) == expected_attempts
    finally:
        provider.close()
