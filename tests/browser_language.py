"""Language preferences use actual browser locales and persisted manual choices."""
import argparse
import asyncio
from pathlib import Path
import socket
import threading
import time
import json

import uvicorn
from playwright.sync_api import expect, sync_playwright

from frontiers.app import create_app


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(create_app(), log_level="error", timeout_graceful_shutdown=2))
        def serve():
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(server.serve(sockets=[listener]))
            finally:
                loop.close()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("Language test server did not start")
                time.sleep(.05)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge")
                errors = []
                cases = [
                    {"locale":"ru-RU", "expected":"ru"},
                    {"locale":"ru-KZ", "expected":"ru"},
                    {"locale":"en-US", "expected":"en"},
                    {"locale":"de-DE", "expected":"en"},
                    {"locale":"de-DE", "languages":["de-DE","ru-RU","en-US"], "expected":"ru"},
                    {"locale":"ru-RU", "languages":["en-GB","ru-RU"], "expected":"en"},
                    {"locale":"ru-RU", "languages":[], "expected":"ru"},
                    {"locale":"ru-RU", "languages":[], "missing_language":True, "expected":"en"},
                    {"locale":"en-US", "saved":"ru", "expected":"ru"},
                    {"locale":"ru-RU", "saved":"en", "expected":"en"},
                    {"locale":"en-US", "saved":"obsolete", "expected":"en"},
                    {"locale":"en-US", "blocked_storage":True, "expected":"en"},
                    {"locale":"ru-RU", "blocked_storage":True, "expected":"ru"},
                ]
                for index, case in enumerate(cases):
                    context = browser.new_context(locale=case["locale"], viewport={"width":1366,"height":768})
                    page = context.new_page()
                    if "languages" in case:
                        context.add_init_script("Object.defineProperty(navigator, 'languages', {get: () => " + json.dumps(case["languages"]) + "})")
                    if case.get("missing_language"):
                        context.add_init_script("Object.defineProperty(navigator, 'language', {get: () => undefined})")
                    if "saved" in case:
                        page.add_init_script("localStorage.setItem('frontiers.language', " + json.dumps(case["saved"]) + ")")
                    if case.get("blocked_storage"):
                        context.add_init_script("Object.defineProperty(window, 'localStorage', {get() { throw new DOMException('Blocked','SecurityError'); }})")
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url)
                    expected = case["expected"]
                    expect(page.locator("html")).to_have_attribute("lang", expected)
                    expect(page.locator("#tutorial-button")).to_be_enabled()
                    expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                    page.locator("#find-match").click()
                    expect(page.locator("#tutorial-offer-dialog")).to_be_visible()
                    expect(page.locator("#tutorial-offer-start")).to_have_text("Начать обучение" if expected == "ru" else "Start tutorial")
                    expect(page.locator("#online-rooms")).to_have_text("Комнат в сети: 0" if expected == "ru" else "Rooms online: 0")
                    if not case.get("blocked_storage") and "saved" not in case:
                        assert page.evaluate("localStorage.getItem('frontiers.language')") is None
                    if index in (0, 2):
                        page.screenshot(path=str(output / f"automatic-{expected}.png"))
                    page.locator("#tutorial-offer-later").click()
                    page.locator("#language-button").click()
                    changed = "en" if expected == "ru" else "ru"
                    expect(page.locator("html")).to_have_attribute("lang", changed)
                    if not case.get("blocked_storage"):
                        assert page.evaluate("localStorage.getItem('frontiers.language')") == changed
                        # Do not seed storage again when verifying persistence.
                        with context.expect_page() as opened:
                            page.evaluate("window.open('/')")
                        other = opened.value
                        expect(other.locator("html")).to_have_attribute("lang", changed)
                        other.close()
                    context.close()
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("13 browser locale cases passed: RU/EN, ordered preferences, fallback, saved choices and unavailable storage.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/browser/language"))
    run(parser.parse_args().output)
