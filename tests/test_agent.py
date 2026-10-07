import pytest

from slotwise.agent import Agent
from slotwise.clinic import Clinic
from slotwise.domain import Policy
from slotwise.providers import Decision, OfflineProvider, ToolCall


class QuietProvider(OfflineProvider):
    name = "test-double"

    def respond(self, session, results):
        return Decision(text="ASK_DATE")


@pytest.fixture
def setup(tmp_path):
    clinic = Clinic(tmp_path / "clinic.sqlite", "2026-10-07")
    agent = Agent(clinic, QuietProvider())
    session = agent.session("patient-a")
    return clinic, agent, session


def offer(agent, session, period="morning"):
    session.preferences = {"specialty": "general", "date": "2026-10-08", "period": period}
    slots = agent.dispatch(
        session,
        "search_slots",
        {
            "specialty": "general",
            "date": "2026-10-08",
            "period": period,
        },
    )["slots"]
    agent.dispatch(session, "prepare_booking", {"slot_id": slots[0]["id"]})
    return slots[0]


def test_model_cannot_commit_without_patient_confirmation(setup):
    clinic, agent, session = setup
    offer(agent, session)
    result = agent.dispatch(session, "commit_booking", {})
    assert result["code"] == "CONFIRMATION_REQUIRED"
    assert clinic.bookings() == []


def test_model_cannot_supply_patient_identity(setup):
    clinic, agent, session = setup
    offer(agent, session)
    result = agent.dispatch(session, "commit_booking", {"patient_id": "patient-b"})
    assert result["code"] == "INVALID_ARGUMENTS"
    assert clinic.bookings() == []


def test_exact_confirmation_books_once_and_duplicate_is_harmless(setup):
    clinic, agent, session = setup
    slot = offer(agent, session)
    agent.turn(session, "yes")
    agent.turn(session, "yes")
    assert session.receipt["slot_id"] == slot["id"]
    assert len(clinic.bookings()) == 1
    assert any(event["kind"] == "consent" for event in session.events)


def test_correction_revokes_old_offer_and_consent(setup):
    clinic, agent, session = setup
    slot = offer(agent, session)
    agent.turn(session, "yes, but make it afternoon")
    assert session.pending is None
    assert session.consent is None
    assert clinic.bookings() == []
    result = agent.turn(session, "confirm", confirm_slot=slot["id"])
    assert result["state"] != "booked"


def test_forged_confirmation_cannot_book_different_slot(setup):
    clinic, agent, session = setup
    offer(agent, session)
    agent.turn(session, "confirm", confirm_slot="unoffered-slot")
    assert clinic.bookings() == []


def test_unoffered_slot_cannot_be_prepared(setup):
    _, agent, session = setup
    result = agent.dispatch(
        session,
        "prepare_booking",
        {
            "slot_id": "general-2026-10-08-0900",
        },
    )
    assert result["code"] == "UNOFFERED_SLOT"


def test_explicit_first_offer_is_selected_even_if_model_would_ask_again(tmp_path):
    agent = Agent(Clinic(tmp_path / "clinic.sqlite", "2026-10-07"), OfflineProvider())
    session = agent.session("patient-a")
    agent.turn(session, "General tomorrow morning")
    first_id = session.offered[0]["id"]
    agent.provider = QuietProvider()
    response = agent.turn(session, "The first available appointment, please.")
    assert response["state"] == "awaiting_confirmation"
    assert session.pending["id"] == first_id
    assert session.receipt is None and session.consent is None


def test_urgency_stops_scheduling_even_after_offer(setup):
    clinic, agent, session = setup
    offer(agent, session)
    agent.turn(session, "I have chest pain and cannot breathe")
    assert session.state == "handoff"
    assert session.pending is None
    assert (
        agent.dispatch(
            session,
            "search_slots",
            {
                "specialty": "general",
                "date": "2026-10-08",
                "period": "morning",
            },
        )["code"]
        == "SESSION_CLOSED"
    )
    assert clinic.bookings() == []


def test_commit_timeout_reconciles_without_second_booking(tmp_path):
    clinic = Clinic(tmp_path / "clinic.sqlite", "2026-10-07")
    agent = Agent(clinic, QuietProvider(), faults={"commit_timeout_once": True})
    session = agent.session("patient-a")
    offer(agent, session)
    agent.turn(session, "yes")
    assert session.receipt is not None
    assert len(clinic.bookings()) == 1
    assert any(e.get("name") == "check_booking_status" for e in session.events)


def test_recovery_requires_new_consent_and_keeps_constraints(tmp_path):
    clinic = Clinic(tmp_path / "clinic.sqlite", "2026-10-07")
    agent = Agent(
        clinic,
        QuietProvider(),
        Policy(version=2, conflict_action="refresh_and_reconfirm"),
        faults={"conflict_once": True},
    )
    session = agent.session("patient-a")
    old = offer(agent, session)
    agent.turn(session, "yes")
    assert session.state == "offered"
    assert session.consent is None
    assert session.pending is None
    assert all(slot["period"] == "morning" for slot in session.offered)
    assert old["id"] not in [slot["id"] for slot in session.offered]
    assert not [b for b in clinic.bookings() if b["patient_id"] == "patient-a"]


def test_provider_failure_exits_safely(setup):
    clinic, agent, session = setup

    class BrokenProvider(QuietProvider):
        name = "test-double"

        def respond(self, session, results):
            raise TimeoutError("sensitive provider internals")

    agent.provider = BrokenProvider()
    result = agent.turn(session, "General tomorrow morning")
    assert result["state"] == "handoff"
    assert "sensitive" not in str(result)
    assert clinic.bookings() == []


def test_tool_cycles_are_bounded(setup):
    _, agent, session = setup

    class LoopProvider(QuietProvider):
        name = "test-double"

        def respond(self, session, results):
            return Decision(calls=[ToolCall("check_booking_status", {})])

    agent.provider = LoopProvider()
    agent.turn(session, "General tomorrow morning")
    assert session.handoff_reason == "step_limit"
    assert len([e for e in session.events if e["kind"] == "tool"]) <= 4
