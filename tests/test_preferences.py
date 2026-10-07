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
