"""Optional genuine browser check. Uses an isolated synthetic server and browser profile."""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    runtime = root / ".slotwise" / ("browser-" + uuid4().hex)
    runtime.mkdir(parents=True)
    shots = root / "examples" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    port = 8001
    address = f"http://127.0.0.1:{port}"
    code = (
        "from pathlib import Path; from slotwise.web import create_app; import uvicorn; "
        f"uvicorn.run(create_app(Path({str(runtime)!r}), mode='offline'), "
        f"host='127.0.0.1', port={port}, log_level='warning')"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        for _ in range(50):
            if process.poll() is not None:
                raise RuntimeError("Isolated smoke-test server did not start.")
            try:
                if httpx.get(address + "/api/config").status_code == 200:
                    break
            except httpx.ConnectError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Smoke-test server was not ready.")
        with sync_playwright() as browser_tool:
            chrome = (
                Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
                / "Google/Chrome/Application/chrome.exe"
            )
            browser = browser_tool.chromium.launch(
                headless=True, executable_path=str(chrome) if chrome.exists() else None
            )
            page = browser.new_page(
                viewport={"width": 1440, "height": 1040}, reduced_motion="reduce"
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: errors.append(message.text) if message.type == "error" else None,
            )
            page.goto(address)
            expect(page.get_by_text("OFFLINE · SCRIPTED", exact=True)).to_be_visible()
            composer_gap = page.evaluate(
                "document.querySelector('.conversation-panel').getBoundingClientRect().bottom "
                "- document.querySelector('.composer').getBoundingClientRect().bottom"
            )
            assert composer_gap < 30, "Chat panel has excessive empty space below the composer"
            message = page.get_by_label("Your message")
            message.fill("What is the code for binary search?")
            message.press("Enter")
            expect(
                page.get_by_text("I can only help with your own clinic appointment.", exact=False)
            ).to_be_visible()
            message.fill("General tomorrow morning")
            message.press("Enter")
            expect(page.get_by_role("button", name="Review", exact=False).first).to_be_visible()
            message.fill("The first available appointment, please.")
            message.press("Enter")
            expect(
                page.get_by_role("button", name="Confirm appointment", exact=True)
            ).to_be_visible()
            message.fill("Yes, but afternoon instead.")
            message.press("Enter")
            expect(
                page.get_by_role("button", name="Confirm appointment", exact=True)
            ).to_have_count(0)
            expect(page.get_by_role("button", name="Review", exact=False).first).to_be_visible()
            target = datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=5)
            message.fill(
                f"Actually, change the date to {target.strftime('%Y/%m/%d')}, afternoon, general."
            )
            message.press("Enter")
            expect(page.get_by_role("button", name="Review", exact=False).first).to_contain_text(
                f"{target.day} {target.strftime('%b')}"
            )
            expect(page.get_by_role("button", name="Confirm appointment", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Review", exact=False).first.click()
            page.get_by_role("button", name="Confirm appointment", exact=True).click()
            expect(
                page.get_by_text("Your appointment is booked. Keep your reference.")
            ).to_be_visible()
            page.evaluate("window.scrollTo(0, 0); document.activeElement.blur()")
            page.screenshot(path=str(shots / "chat-desktop.png"), full_page=True)
            page.get_by_role("button", name="Evaluation lab", exact=False).click()
            page.get_by_label("Runs per scenario").select_option("2")
            page.get_by_role("button", name="Run improvement loop", exact=False).click()
            expect(page.get_by_text("Promoted", exact=True)).to_be_visible(timeout=30000)
            expect(page.get_by_text("100/100", exact=True)).to_be_visible()
            page.evaluate("window.scrollTo(0, 0); document.activeElement.blur()")
            page.screenshot(path=str(shots / "eval-desktop.png"), full_page=True)
            page.get_by_role(
                "button", name="Inspect Slot taken before commit, run 1", exact=True
            ).click()
            expect(page.get_by_text("CONFLICT_RECOVERY_INCOMPLETE", exact=True)).to_be_visible()
            expect(
                page.get_by_role("paragraph").filter(
                    has_text="That appointment was taken before booking."
                )
            ).to_be_visible()
            page.get_by_role("button", name="Patient conversation", exact=False).click()
            page.set_viewport_size({"width": 375, "height": 812})
            page.evaluate("window.scrollTo(0, 0); document.activeElement.blur()")
            page.screenshot(path=str(shots / "chat-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                "Mobile overflow"
            )
            assert not errors, errors
            browser.close()
        print(
            "Browser PASS: keyboard chat, correction, confirmation, eval evidence, mobile, reduced motion."
        )
        print("Screenshots: " + str(shots))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
