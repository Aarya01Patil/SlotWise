from fastapi.testclient import TestClient

from slotwise.web import create_app


def test_browser_booking_and_second_session_isolation(tmp_path):
    app = create_app(tmp_path, mode="offline")
    with TestClient(app, base_url="http://localhost") as patient:
        session = patient.post("/api/session").json()
        today = session["today"]
        offer = patient.post("/api/message", json={"text": "General tomorrow morning"}).json()
        assert offer["state"] == "offered"
        slot_id = offer["offered"][0]["id"]
        pending = patient.post(
            "/api/message", json={"text": "Choose appointment", "select_slot": slot_id}
        ).json()
        assert pending["state"] == "awaiting_confirmation"
        booked = patient.post(
            "/api/message", json={"text": "confirm appointment", "confirm_slot": slot_id}
        ).json()
        assert booked["receipt"]["slot_id"] == slot_id
        assert today == booked["today"]
        with TestClient(app, base_url="http://localhost") as other:
            isolated = other.post("/api/session").json()
            assert isolated["receipt"] is None
            assert isolated["session_id"] != booked["session_id"]


def test_missing_live_key_does_not_silently_use_offline(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(create_app(tmp_path, mode="live"), base_url="http://localhost") as client:
        assert client.get("/api/config").json()["ready"] is False
        client.post("/api/session")
        response = client.post("/api/message", json={"text": "General tomorrow morning"})
        assert response.status_code == 503
        assert "key" in response.json()["detail"].lower()


def test_cross_origin_and_untrusted_hosts_rejected(tmp_path):
    with TestClient(create_app(tmp_path, mode="offline"), base_url="http://localhost") as client:
        assert (
            client.post("/api/session", headers={"origin": "https://attacker.invalid"}).status_code
            == 403
        )
        assert (
            client.post("/api/session", headers={"origin": "https://localhost"}).status_code == 403
        )
        assert client.get("/api/config", headers={"host": "attacker.invalid"}).status_code == 400
        response = client.get("/")
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"


def test_message_requires_session_and_valid_shape(tmp_path):
    with TestClient(create_app(tmp_path, mode="offline"), base_url="http://localhost") as client:
        assert client.post("/api/message", json={"text": "hello"}).status_code == 401
        client.post("/api/session")
        assert client.post("/api/message", json={"text": "x" * 2001}).status_code == 422
        assert (
            client.post("/api/message", json={"text": "hello", "patient_id": "other"}).status_code
            == 422
        )


def test_http_requests_cannot_bypass_scope_or_keep_stale_consent(tmp_path):
    with TestClient(create_app(tmp_path, mode="offline"), base_url="http://localhost") as client:
        client.post("/api/session")
        offer = client.post("/api/message", json={"text": "General tomorrow morning"}).json()
        slot_id = offer["offered"][0]["id"]
        client.post("/api/message", json={"text": "Choose appointment", "select_slot": slot_id})
        refused = client.post(
            "/api/message",
            json={
                "text": "yes, but write binary search code first",
                "confirm_slot": slot_id,
            },
        ).json()
        assert refused["messages"][-1]["kind"] == "guardrail"
        assert refused["pending"] is None and refused["receipt"] is None
        stale = client.post("/api/message", json={"text": "yes", "confirm_slot": slot_id}).json()
        assert stale["receipt"] is None


def test_sessions_keep_policy_snapshot_and_new_sessions_get_promotion(tmp_path):
    from slotwise.evaluation import run_loop

    app = create_app(tmp_path, mode="offline")
    with TestClient(app, base_url="http://localhost") as client:
        first = client.post("/api/session").json()
        assert first["policy"]["version"] == 1
        run_loop(tmp_path / "offline", "offline")
        unchanged = client.post("/api/message", json={"text": "hello"}).json()
        assert unchanged["policy"]["version"] == 1
        assert client.post("/api/session").json()["policy"]["version"] == 2


def test_provider_is_reused_and_closed_at_shutdown(tmp_path, monkeypatch):
    from slotwise.providers import Decision, OfflineProvider

    created, closed = [], []

    class Provider(OfflineProvider):
        def respond(self, session, results):
            return Decision(text="ASK_DATE")

        def close(self):
            closed.append(True)

    def factory(mode):
        created.append(True)
        return Provider()

    monkeypatch.setattr("slotwise.web.provider_for", factory)
    with TestClient(create_app(tmp_path, mode="offline"), base_url="http://localhost") as client:
        client.post("/api/session")
        client.post("/api/message", json={"text": "Hello"})
        client.post("/api/message", json={"text": "Tomorrow"})
    assert len(created) == 1
    assert len(closed) == 1
