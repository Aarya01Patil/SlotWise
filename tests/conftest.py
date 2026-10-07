"""Keep test databases in a fresh workspace folder, avoiding shared Windows temp ACLs."""

from pathlib import Path
from uuid import uuid4


def pytest_configure(config):
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parents[1]
        target = (root / ".slotwise" / ("tests-" + uuid4().hex)).resolve()
        if not target.is_relative_to(root) or target.exists():
            raise RuntimeError("Test temporary directory must be new and inside the workspace.")
        config.option.basetemp = str(target)
