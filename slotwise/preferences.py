"""Small explicit scheduling fragments. Unsupported preferences remain unresolved."""

import re
from datetime import date, timedelta

from slotwise.guardrails import REPLIES, normalized

SPECIALTIES = {
    "general": "general",
    "gp": "general",
    "dental": "dental",
    "dentist": "dental",
    "dermatology": "dermatology",
    "dermatologist": "dermatology",
}
UNAVAILABLE = re.compile(
    r"\b(orthopaedic|orthopedic|orthopaedics|orthopedics|cardiology|neurology)\b", re.IGNORECASE
)
UNAVAILABLE_SPECIALTIES = {
    "orthopaedic",
    "orthopedic",
    "orthopaedics",
    "orthopedics",
    "cardiology",
    "neurology",
}
DATE_PATTERN = r"\d{4}-\d{2}-\d{2}|\d{4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2}/\d{4}"


def safe_fragment(text: str) -> bool:
    """Exact bounded grammar only; mentioning a specialty does not authorize arbitrary text."""
    text = normalized(text).lower().strip(" .!")
    return text in {
        *SPECIALTIES,
        *UNAVAILABLE_SPECIALTIES,
        "morning",
        "afternoon",
        "evening",
        "any time",
        "anytime",
        "tomorrow",
        "first",
        "first one",
        "the first available appointment, please",
    } or bool(re.fullmatch(DATE_PATTERN, text))


def has_scheduling_content(text: str) -> bool:
    """Detect if text contains scheduling indicators that indicate appointment booking context."""
    text = normalized(text).lower()
    if any(re.search(rf"\b{alias}\b", text) for alias in SPECIALTIES):
        return True
    if UNAVAILABLE.search(text):
        return True
    if re.search(rf"\b(?:{DATE_PATTERN})\b", text):
        return True
    return bool(re.search(r"\b(tomorrow|morning|afternoon|evening|appointment|visit)\b", text))


def collect(session, text: str) -> str | None:
    text = normalized(text).lower()
    prefs, issues = session.preferences, session.preference_issues
    # Do not turn alternatives or negation into a silently chosen constraint.
    if re.search(r"\b(?:not|except|either)\b", text):
        return REPLIES["ASK_DETAILS"]
    found = {value for alias, value in SPECIALTIES.items() if re.search(rf"\b{alias}\b", text)}
    if len(found) == 1:
        prefs["specialty"] = found.pop()
        issues.pop("specialty", None)
    elif len(found) > 1:
        prefs.pop("specialty", None)
        return REPLIES["ASK_SPECIALTY"]
    elif unavailable := UNAVAILABLE.search(text):
        prefs.pop("specialty", None)
        issues["specialty"] = unavailable.group()
    match = re.search(rf"\b(?:{DATE_PATTERN})\b", text)
    target = None
    if match:
        raw = match.group()
        try:
            if "/" in raw:
                parts = raw.split("/")
                if len(parts[0]) == 4:
                    year, month, day = map(int, parts)
                else:
                    day, month, year = map(int, parts)
                target = date(year, month, day)
            else:
                target = date.fromisoformat(raw)
        except ValueError:
            prefs.pop("date", None)
            issues["date"] = "invalid"
    elif "tomorrow" in text:
        target = date.fromisoformat(session.today) + timedelta(days=1)
    elif re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text):
        prefs.pop("date", None)
        issues["date"] = "ambiguous"
    if target:
        prefs["date"] = target.isoformat()
        if target <= date.fromisoformat(session.today):
            issues["date"] = "past_or_today"
        else:
            issues.pop("date", None)
    periods = [period for period in ("morning", "afternoon") if re.search(rf"\b{period}\b", text)]
    if len(periods) == 1:
        prefs["period"] = periods[0]
        issues.pop("period", None)
    elif len(periods) > 1:
        prefs.pop("period", None)
        return REPLIES["ASK_PERIOD"]
    elif re.search(r"\b(anytime|any time)\b", text):
        prefs["period"] = "any"
        issues.pop("period", None)
    elif "evening" in text:
        prefs.pop("period", None)
        issues["period"] = "evening"
    if "specialty" in issues:
        return "That specialty is not available in this demo. " + REPLIES["ASK_SPECIALTY"]
    if "period" in issues:
        return "Evening appointments are not available in this demo. " + REPLIES["ASK_PERIOD"]
    if issues.get("date") == "past_or_today":
        return (
            "This demo books from tomorrow onward. Please choose a future date; "
            + session.today
            + " is the clinic's current date."
        )
    if issues.get("date") == "invalid":
        return (
            "That calendar date is invalid. Please give a valid date as DD/MM/YYYY or YYYY-MM-DD."
        )
    if "date" in issues:
        return REPLIES["ASK_DATE"]
    # Missing constraints must be requested before the model can propose a search.
    if session.state == "collecting":
        for key, token in (
            ("specialty", "ASK_SPECIALTY"),
            ("date", "ASK_DATE"),
            ("period", "ASK_PERIOD"),
        ):
            if key not in prefs:
                return REPLIES[token]
    return None
