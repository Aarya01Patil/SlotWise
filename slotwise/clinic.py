"""Synthetic clinic. Database constraints are the final booking authority."""

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4


class ClinicError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Clinic:
    def __init__(self, path: Path, today: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.today = date.fromisoformat(today)
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS slots (
                    id TEXT PRIMARY KEY, specialty TEXT NOT NULL, doctor TEXT NOT NULL,
                    date TEXT NOT NULL, period TEXT NOT NULL, starts_at TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL, location TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bookings (
                    id TEXT PRIMARY KEY, patient_id TEXT NOT NULL UNIQUE,
                    slot_id TEXT NOT NULL UNIQUE REFERENCES slots(id),
                    attempt_key TEXT NOT NULL, UNIQUE(patient_id, attempt_key)
                );
            """)
            for day in range(1, 8):
                visit_date = (self.today + timedelta(days=day)).isoformat()
                for specialty, doctor in [
                    ("general", "Dr Nila Shah"),
                    ("dental", "Dr Maya Rao"),
                    ("dermatology", "Dr Arun Sen"),
                ]:
                    for hour in [9, 10, 14, 15]:
                        db.execute(
                            "INSERT OR IGNORE INTO slots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                f"{specialty}-{visit_date}-{hour:02d}00",
                                specialty,
                                doctor,
                                visit_date,
                                "morning" if hour < 12 else "afternoon",
                                f"{visit_date}T{hour:02d}:00:00+05:30",
                                30,
                                "SlotWise Demo Clinic",
                            ),
                        )
            db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def search(self, specialty: str, visit_date: str, period: str):
        try:
            target = date.fromisoformat(visit_date)
        except ValueError as error:
            raise ClinicError("INVALID_DATE") from error
        if target <= self.today or target > self.today + timedelta(days=30):
            raise ClinicError("INVALID_DATE")
        if specialty not in {"general", "dental", "dermatology"}:
            raise ClinicError("UNSUPPORTED_SPECIALTY")
        if period not in {"morning", "afternoon", "any"}:
            raise ClinicError("INVALID_PERIOD")
        with closing(self.connect()) as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT s.* FROM slots s LEFT JOIN bookings b ON b.slot_id=s.id "
                    "WHERE b.id IS NULL AND s.specialty=? AND s.date=? "
                    "AND (?='any' OR s.period=?) ORDER BY s.starts_at LIMIT 4",
                    (specialty, visit_date, period, period),
                )
            ]

    def book(self, patient_id: str, slot_id: str, attempt_key: str):
        with closing(self.connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                prior = db.execute(
                    "SELECT * FROM bookings WHERE patient_id=? AND attempt_key=?",
                    (patient_id, attempt_key),
                ).fetchone()
                if prior:
                    if prior["slot_id"] != slot_id:
                        raise ClinicError("IDEMPOTENCY_MISMATCH")
                    db.commit()
                    return self.status(patient_id, attempt_key)
                if db.execute(
                    "SELECT 1 FROM bookings WHERE patient_id=?", (patient_id,)
                ).fetchone():
                    raise ClinicError("ALREADY_BOOKED")
                if not db.execute("SELECT 1 FROM slots WHERE id=?", (slot_id,)).fetchone():
                    raise ClinicError("UNKNOWN_SLOT")
                if db.execute("SELECT 1 FROM bookings WHERE slot_id=?", (slot_id,)).fetchone():
                    raise ClinicError("SLOT_CONFLICT")
                db.execute(
                    "INSERT INTO bookings VALUES (?, ?, ?, ?)",
                    ("SW-" + uuid4().hex[:10].upper(), patient_id, slot_id, attempt_key),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
        return self.status(patient_id, attempt_key)

    def status(self, patient_id: str, attempt_key: str):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT b.*, s.specialty, s.doctor, s.date, s.period, s.starts_at, "
                "s.duration_minutes, s.location FROM bookings b JOIN slots s ON s.id=b.slot_id "
                "WHERE b.patient_id=? AND b.attempt_key=?",
                (patient_id, attempt_key),
            ).fetchone()
            return dict(row) if row else None

    def bookings(self):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM bookings ORDER BY id")]
