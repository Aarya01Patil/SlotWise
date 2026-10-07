from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = Field(default=1, ge=1)
    conflict_action: Literal["handoff", "refresh_and_reconfirm"] = "handoff"


BASELINE = Policy()


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specialty: Literal["general", "dental", "dermatology"]
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    period: Literal["morning", "afternoon", "any"]


class PrepareArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_id: str = Field(min_length=1, max_length=100)


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HandoffArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["unsupported", "no_availability", "patient_request", "tool_error"]


@dataclass
class Session:
    patient_id: str
    today: str
    policy: Policy = BASELINE
    id: str = field(default_factory=lambda: uuid4().hex)
    state: str = "collecting"
    preferences: dict = field(default_factory=dict)
    preference_issues: dict = field(default_factory=dict)
    offered: list = field(default_factory=list)
    pending: dict | None = None
    consent: dict | None = None
    attempt_key: str | None = None
    receipt: dict | None = None
    handoff_reason: str | None = None
    events: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    history: list = field(default_factory=list)
    history_turn: int = 0
    patient_turns: int = 0
    recovery_attempts: int = 0

    def event(self, kind: str, **data):
        record = {"seq": len(self.events) + 1, "kind": kind, **data}
        self.events.append(record)
        return record

    def public(self):
        return {
            "session_id": self.id,
            "state": self.state,
            "today": self.today,
            "timezone": "Asia/Kolkata",
            "preferences": self.preferences,
            "offered": self.offered,
            "pending": self.pending,
            "receipt": self.receipt,
            "handoff_reason": self.handoff_reason,
            "messages": self.messages,
            "policy": self.policy.model_dump(),
        }
