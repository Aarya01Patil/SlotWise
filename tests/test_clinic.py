from concurrent.futures import ThreadPoolExecutor

import pytest

from slotwise.clinic import Clinic, ClinicError


@pytest.fixture
def clinic(tmp_path):
    return Clinic(tmp_path / "clinic.sqlite", "2026-10-07")


def test_slot_transaction_has_one_winner_under_concurrency(clinic):
    slot = clinic.search("general", "2026-10-08", "morning")[0]

    def book(patient):
        try:
            return clinic.book(patient, slot["id"], patient)["id"]
        except ClinicError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(book, ["patient-a", "patient-b"]))
    assert results.count("SLOT_CONFLICT") == 1
    assert len(clinic.bookings()) == 1


def test_idempotent_retry_returns_same_receipt(clinic):
    slot = clinic.search("general", "2026-10-08", "morning")[0]
    first = clinic.book("patient-a", slot["id"], "attempt-1")
    assert clinic.book("patient-a", slot["id"], "attempt-1") == first
    assert len(clinic.bookings()) == 1


def test_patient_cannot_read_another_patients_booking(clinic):
    slot = clinic.search("general", "2026-10-08", "morning")[0]
    clinic.book("patient-a", slot["id"], "attempt-1")
    assert clinic.status("patient-b", "attempt-1") is None


def test_idempotency_key_cannot_be_reused_for_different_slot(clinic):
    slots = clinic.search("general", "2026-10-08", "morning")
    clinic.book("patient-a", slots[0]["id"], "attempt-1")
    with pytest.raises(ClinicError, match="IDEMPOTENCY_MISMATCH"):
        clinic.book("patient-a", slots[1]["id"], "attempt-1")


def test_patient_has_only_one_active_appointment(clinic):
    slots = clinic.search("general", "2026-10-08", "morning")
    clinic.book("patient-a", slots[0]["id"], "attempt-1")
    with pytest.raises(ClinicError, match="ALREADY_BOOKED"):
        clinic.book("patient-a", slots[1]["id"], "attempt-2")


def test_search_rejects_past_dates(clinic):
    with pytest.raises(ClinicError, match="INVALID_DATE"):
        clinic.search("general", "2026-10-06", "morning")
