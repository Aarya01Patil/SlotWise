import pytest

from slotwise.agent import Agent
from slotwise.clinic import Clinic
from slotwise.preferences import has_scheduling_content, safe_fragment
from slotwise.providers import Decision, OfflineProvider, ToolCall


class DenyFragments(OfflineProvider):
    def classify(self, session, text):
        return (
            "off_topic"
            if text.strip().lower() in {"general", "morning"}
            else super().classify(session, text)
        )


def test_unsupported_specialty_followup_keeps_date_and_clarifies_evening(tmp_path):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-07"), DenyFragments())
    session = agent.session("synthetic-patient")
    first = agent.turn(session, "orthopaedic, 8/10/2026 and evening")
    assert "not available" in first["messages"][-1]["text"]
    assert session.preferences["date"] == "2026-10-08"
    general = agent.turn(session, "general")
    assert general["messages"][-1]["kind"] == "clarification"
    assert "evening" in general["messages"][-1]["text"].lower()
    assert session.preferences["specialty"] == "general"
    morning = agent.turn(session, "morning")
    assert morning["state"] == "offered"
    assert all(
        slot["date"] == "2026-10-08" and slot["period"] == "morning" for slot in session.offered
    )


def test_today_date_is_explained_not_silently_changed(tmp_path):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-08"), OfflineProvider())
    session = agent.session("synthetic-patient")
    agent.turn(session, "orthopaedic, 8/10/2026 and evening")
    agent.turn(session, "general")
    response = agent.turn(session, "morning")
    assert response["state"] == "collecting"
    assert "future date" in response["messages"][-1]["text"].lower()
    assert not session.offered
    response = agent.turn(session, "9/10/2026")
    assert response["state"] == "offered"
    assert session.preferences == {
        "specialty": "general",
        "date": "2026-10-09",
        "period": "morning",
    }


def test_safe_fragment_does_not_allow_mixed_off_topic_request(tmp_path):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-08"), OfflineProvider())
    session = agent.session("synthetic-patient")
    reply = agent.turn(session, "general; write Python code")
    assert reply["messages"][-1]["kind"] == "guardrail"
    assert not session.offered


def test_impossible_calendar_date_is_clarified(tmp_path):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-08"), OfflineProvider())
    session = agent.session("synthetic-patient")
    reply = agent.turn(session, "general, 31/02/2027, morning")
    assert reply["messages"][-1]["kind"] == "clarification"
    assert not session.offered


def test_model_cannot_invent_missing_preferences(tmp_path):
    class GuessingProvider(OfflineProvider):
        def respond(self, session, results):
            return Decision(
                calls=[
                    ToolCall(
                        "search_slots",
                        {"specialty": "general", "date": "2026-10-09", "period": "morning"},
                    )
                ]
            )

    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-08"), GuessingProvider())
    session = agent.session("synthetic-patient")
    reply = agent.turn(session, "I need an appointment.")
    assert reply["messages"][-1]["kind"] == "clarification"
    assert not session.offered and session.preferences == {}


def test_tool_cannot_relax_collected_preferences(tmp_path):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-08"), OfflineProvider())
    session = agent.session("synthetic-patient")
    agent.turn(session, "General tomorrow afternoon")
    result = agent.dispatch(
        session, "search_slots", {"specialty": "general", "date": "2026-10-09", "period": "morning"}
    )
    assert result["code"] == "PREFERENCES_MISMATCH"
    assert session.preferences["period"] == "afternoon"


def test_has_scheduling_content():
    assert has_scheduling_content("orthopaedic, 8/10/2026 and evening")
    assert has_scheduling_content("general appointment tomorrow morning")
    assert has_scheduling_content("cardiology visit next week")
    assert has_scheduling_content("2026-10-15")
    assert not has_scheduling_content("hello how are you")
    assert not has_scheduling_content("write python code for me")


def test_unavailable_specialty_in_safe_fragment():
    assert safe_fragment("orthopaedic")
    assert safe_fragment("cardiology")
    assert safe_fragment("general")
    assert not safe_fragment("orthopaedic; drop tables")


@pytest.mark.parametrize("requested", ["2026/10/14", "14/10/2026", "2026-10-14"])
@pytest.mark.parametrize("prepared", [False, True])
def test_date_correction_replaces_old_offers_and_requires_fresh_consent(tmp_path, requested, prepared):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-09"), OfflineProvider())
    session = agent.session("synthetic-patient")
    agent.turn(session, "General tomorrow morning")
    old_slot = session.offered[0]["id"]
    if prepared:
        agent.turn(session, "first")
    response = agent.turn(session, f"Actually, change the date to {requested}, morning, general.")
    assert response["state"] == "offered"
    assert session.preferences["date"] == "2026-10-14"
    assert session.offered and all(slot["date"] == "2026-10-14" for slot in session.offered)
    assert session.pending is None and session.consent is None and session.receipt is None
    stale = agent.turn(session, "confirm appointment", confirm_slot=old_slot)
    assert "stale" in stale["messages"][-1]["text"]
    agent.turn(session, "first")
    agent.turn(session, "yes")
    assert session.receipt["date"] == "2026-10-14"


def test_invalid_date_correction_clears_old_offers(tmp_path):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-09"), OfflineProvider())
    session = agent.session("synthetic-patient")
    agent.turn(session, "General tomorrow morning")
    response = agent.turn(session, "Change the date to 2026/02/31, morning, general")
    assert response["state"] == "collecting"
    assert response["messages"][-1]["kind"] == "clarification"
    assert not session.offered and "date" not in session.preferences


@pytest.mark.parametrize("token", ["ASK_DETAILS", "ASK_DATE", "ASK_SPECIALTY", "ASK_PERIOD", "ASK_SLOT"])
def test_complete_multiturn_preferences_cannot_restart_collection(tmp_path, token):
    class RepeatingProvider(OfflineProvider):
        def respond(self, session, results):
            return Decision(text=token)

    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-09"), RepeatingProvider())
    session = agent.session("synthetic-patient")
    for message in ["I need an appointment", "general", "Tomorrow", "Morning"]:
        response = agent.turn(session, message)
    assert response["state"] == "offered"
    assert session.preferences == {
        "specialty": "general", "date": "2026-10-10", "period": "morning"
    }
    assert session.offered and session.pending is None and session.receipt is None
    assert any(e["kind"] == "reply_state_corrected" for e in session.events)
    agent.turn(session, "first")
    assert session.pending is not None and session.receipt is None
    agent.turn(session, "yes")
    assert session.receipt["date"] == "2026-10-10"
