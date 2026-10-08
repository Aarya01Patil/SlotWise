"""Exercise pytest startup in a checkout with no ignored runtime directories."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_fresh_checkout_supports_pytest_temporary_databases(tmp_path):
    checkout = tmp_path / "fresh-checkout"
    tests = checkout / "tests"
    tests.mkdir(parents=True)
    (checkout / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    shutil.copyfile(Path(__file__).with_name("conftest.py"), tests / "conftest.py")
    (tests / "test_probe.py").write_text(
        "from pathlib import Path\n"
        "def test_workspace_temp(tmp_path):\n"
        "    assert tmp_path.is_dir()\n"
        "    assert tmp_path.is_relative_to(Path(__file__).resolve().parents[1] / '.slotwise')\n",
        encoding="utf-8",
    )
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
