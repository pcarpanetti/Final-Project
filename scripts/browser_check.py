"""Drive the real web app in a real browser, end to end, as a person would, offline.

Needs Playwright (pip install playwright) and Microsoft Edge or Chrome. Not a dependency of the project.
Saves screenshots to docs/screens/ and fails on any browser console error.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screens"
PORT = 8791
URL = f"http://127.0.0.1:{PORT}/"


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="rwweb"))
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "RISKWATCH_WEB_HOME": str(workspace)}
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY"):
        env.pop(name, None)
    server = subprocess.Popen([sys.executable, "-m", "riskwatch", "web", "--port", str(PORT), "--no-browser"], env=env, cwd=ROOT)
    problems: list[str] = []
    try:
        time.sleep(3)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1320, "height": 900})
            page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(str(e)))

            def shot(name: str) -> None:
                page.wait_for_timeout(350)
                page.screenshot(path=SHOTS / f"{name}.png", full_page=True)

            # Keep personal account details out of the committed screenshots.
            page.route("**/api/claude", lambda r: r.fulfill(json={"installed": True, "logged_in": True,
                                                                  "email": "you@example.com", "plan": "pro"}))

            # 1. Connect
            page.goto(URL)
            expect(page.locator("#side-download")).to_have_attribute("aria-disabled", "true")
            expect(page.get_by_role("heading", name="Connect a model")).to_be_visible()
            page.wait_for_timeout(1500)
            shot("1-connect")
            page.get_by_text("OpenRouter", exact=True).click()
            expect(page.locator("#base-url")).to_have_value("https://openrouter.ai/api/v1")
            expect(page.locator("#api-key")).to_be_visible()
            shot("1b-connect-api")
            page.get_by_text("Offline demo", exact=True).click()
            page.locator("#continue").click()
            expect(page.locator(".toast.err")).to_contain_text("name")
            page.locator("#name").fill("Pablo Carpanetti")
            page.locator("#test").click()
            expect(page.locator(".notice.good")).to_contain_text("Connected")
            page.locator("#continue").click()

            # 2. Run
            expect(page.get_by_role("heading", name="Run the workflow")).to_be_visible()
            page.get_by_text("Crash month", exact=True).click()
            page.get_by_text("I will review them", exact=True).click()
            shot("2-run-setup")
            page.locator("#start").click()
            expect(page.get_by_text("days processed")).to_be_visible()
            page.wait_for_timeout(5000)
            shot("2b-run-progress")
            expect(page.get_by_role("link", name="Open dashboard")).to_be_visible(timeout=120000)
            shot("2c-run-finished")

            # 3. Approve
            page.get_by_role("link", name="Approve").first.click()
            expect(page.get_by_role("heading", name="Why this needs you")).to_be_visible()
            shot("3-approvals")
            first = page.locator(".list button.on").inner_text().splitlines()[0]
            page.locator("#approve").click()
            expect(page.locator(".list button", has_text=first)).to_have_count(0, timeout=20000)
            page.get_by_role("button", name="Request changes").click()
            expect(page.locator(".toast.err").last).to_contain_text("note")
            page.locator("#note").fill("Please lead with the largest risk driver.")
            page.get_by_role("button", name="Request changes").click()
            page.wait_for_timeout(2500)
            page.once("dialog", lambda d: d.accept())
            page.get_by_role("button", name="Approve all").click()
            expect(page.get_by_text("Nothing is waiting for you.")).to_be_visible(timeout=60000)

            # Results
            page.locator("nav a[href=\"#/dashboard\"]").click()
            expect(page.get_by_text("Did VaR hold?")).to_be_visible()
            # The download stays in the sidebar on every page, not only on Reports.
            with page.expect_download() as from_sidebar:
                page.locator("#side-download").click()
            assert from_sidebar.value.suggested_filename == "riskwatch-output.zip"
            box = page.locator(".chart-wrap svg").bounding_box()
            page.mouse.move(box["x"] + box["width"] * 0.7, box["y"] + box["height"] * 0.5)
            expect(page.locator(".tip")).to_be_visible()
            shot("4-dashboard")

            page.locator("nav a[href=\"#/reports\"]").click()
            expect(page.locator(".memo h1")).to_contain_text("Daily Risk Memo")
            shot("5-reports")
            with page.expect_download() as download:
                page.locator("#download").click()
            target = workspace / "out.zip"
            download.value.save_as(target)
            assert target.stat().st_size > 2000

            page.locator("nav a[href=\"#/runs\"]").click()
            page.get_by_role("link", name="eod-2020-03-09").click()
            expect(page.get_by_role("heading", name="Stages")).to_be_visible()
            page.get_by_role("button", name="Checks").click()
            expect(page.get_by_text("Recompute metrics").first).to_be_visible()
            shot("6-run-checks")
            page.get_by_role("button", name="Agent replies").click()
            expect(page.locator("pre.code").first).to_be_visible()

            page.locator("nav a[href=\"#/improve\"]").click()
            expect(page.get_by_role("heading", name="Candidates")).to_be_visible()
            shot("7-improve")
            page.locator("nav a[href=\"#/help\"]").click()
            expect(page.get_by_text("Getting a full output")).to_be_visible()

            page.set_viewport_size({"width": 400, "height": 800})
            page.goto(URL + "#/dashboard")
            expect(page.get_by_text("Did VaR hold?")).to_be_visible()
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if overflow > 1:
                problems.append(f"page overflows sideways by {overflow}px at phone width")
            shot("8-phone")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        shutil.rmtree(workspace, ignore_errors=True)
    real = [p for p in problems if "favicon" not in p]
    print("BROWSER CHECK", "PASSED" if not real else f"FAILED: {real}")
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
