"""Explicit public-demo boundary; local development remains loopback by default."""

import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Hosting:
    public: bool
    hostname: str | None
    operator_token: str

    @classmethod
    def from_env(cls):
        public = os.getenv("SLOTWISE_PUBLIC", "0") == "1"
        hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("SLOTWISE_HOSTNAME")
        token = os.getenv("SLOTWISE_OPERATOR_TOKEN", "")
        if public:
            if (
                not hostname
                or urlsplit("https://" + hostname).netloc != hostname
                or any(char in hostname for char in "/*@: ")
            ):
                raise ValueError(
                    "Public demo requires an exact SLOTWISE_HOSTNAME or Render hostname."
                )
            if token and len(token) < 24:
                raise ValueError("SLOTWISE_OPERATOR_TOKEN must contain at least 24 characters.")
        return cls(public, hostname if public else None, token)

    def authorize_operator(self, supplied: str) -> bool:
        return not self.public or (
            bool(self.operator_token) and secrets.compare_digest(supplied, self.operator_token)
        )


class DemoBudget:
    """Process-local demo limits, deliberately insufficient as production abuse protection."""

    def __init__(self, daily_messages=60):
        self.daily_messages = daily_messages
        self.day = ""
        self.used = 0
        self.windows = {}
        self.lock = threading.Lock()

    def allow(self, address: str, route: str) -> bool:
        with self.lock:
            today = datetime.now(UTC).date().isoformat()
            if today != self.day:
                self.day, self.used = today, 0
                self.windows.clear()
            now = time.monotonic()
            # Bound limiter memory even when requests come from many addresses.
            expired = [
                key for key, times in self.windows.items() if not times or now - times[-1] >= 3600
            ]
            for key in expired:
                self.windows.pop(key)
            key = (address, route)
            if key not in self.windows and len(self.windows) >= 1000:
                return False
            times = self.windows.setdefault(key, deque())
            while times and now - times[0] >= 3600:
                times.popleft()
            limit = 8 if route == "/api/session" else 20
            if len(times) >= limit or sum(now - stamp < 60 for stamp in times) >= 6:
                return False
            if route == "/api/message":
                if self.used >= self.daily_messages:
                    return False
                self.used += 1
            times.append(now)
            return True
