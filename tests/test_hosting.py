import pytest
from fastapi.testclient import TestClient

from slotwise.hosting import DemoBudget, Hosting
from slotwise.web import create_app


def test_public_demo_requires_exact_host_and_long_operator_secret(monkeypatch):
    monkeypatch.setenv("SLOTWISE_PUBLIC", "1")
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    monkeypatch.setenv("SLOTWISE_HOSTNAME", "*.example.com")
    with pytest.raises(ValueError, match="exact"):
        Hosting.from_env()
    monkeypatch.setenv("SLOTWISE_HOSTNAME", "slotwise.example.com")
    monkeypatch.setenv("SLOTWISE_OPERATOR_TOKEN", "short")
    with pytest.raises(ValueError, match="24"):
        Hosting.from_env()


def test_public_operator_access_origin_and_secure_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOTWISE_PUBLIC", "1")
    monkeypatch.setenv("SLOTWISE_HOSTNAME", "slotwise.example.com")
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    monkeypatch.setenv("SLOTWISE_OPERATOR_TOKEN", "synthetic-operator-token-123456")
    with TestClient(
        create_app(tmp_path, "offline"), base_url="https://slotwise.example.com"
    ) as client:
        assert client.get("/healthz").json()["synthetic"] is True
        assert client.get("/api/config").json()["eval_requires_token"] is True
        response = client.post("/api/session", headers={"origin": "https://slotwise.example.com"})
        assert "Secure" in response.headers["set-cookie"]
        assert client.post("/api/evals", json={"repeats": 1}).status_code == 403
        assert (
            client.post(
                "/api/evals", json={"repeats": 1}, headers={"x-slotwise-operator": "wrong"}
            ).status_code
            == 403
        )
        assert (
            client.post("/api/session", headers={"origin": "https://attacker.invalid"}).status_code
            == 403
        )
        assert client.get("/api/config", headers={"host": "attacker.invalid"}).status_code == 400


def test_public_limits_bound_sessions_and_total_chat_cost():
    budget = DemoBudget(daily_messages=2)
    assert budget.allow("patient-a", "/api/message")
    assert budget.allow("patient-b", "/api/message")
    assert not budget.allow("patient-c", "/api/message")
    for _ in range(6):
        assert budget.allow("same-address", "/api/session")
    assert not budget.allow("same-address", "/api/session")
