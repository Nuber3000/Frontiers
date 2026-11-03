"""Exercise the local worker with the real browser CSP and without network play."""

import argparse
import asyncio
import socket
import threading
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from frontiers.app import create_app


def run(channel, language):
    app = create_app()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=2))
        thread = threading.Thread(target=lambda: asyncio.run(server.serve(sockets=[listener])), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("Test server did not start")
                time.sleep(0.05)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=channel)
                context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
                page = context.new_page()
                errors, online_requests, web_sockets = [], [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("request", lambda request: online_requests.append(request.url) if "/api/rooms" in request.url else None)
                page.on("websocket", lambda ws: web_sockets.append(ws.url))
                page.goto(f"http://127.0.0.1:{port}")
                if language == "en":
                    page.locator("#language-button").click()
                    expect(page.locator("html")).to_have_attribute("lang", "en")
                    expect(page.locator("#play-bot")).to_have_text("Play against bot")
                page.locator("#player-name").fill("Тест")
                page.locator("#play-bot").click()
                try:
                    expect(page.locator("#connection")).to_have_text(
                        "Local game" if language == "en" else "Локальная игра", timeout=25000)
                except AssertionError as error:
                    raise AssertionError(f"Worker startup failed: {errors}") from error
                expect(page.locator("#copy-invite")).to_be_hidden()
                context.set_offline(True)
                page.locator("#ready-button").click()
                page.locator("#mulligan-button").click()
                for _ in range(3):
                    page.locator("#pass-button:enabled, #result-dialog[open]").first.wait_for(timeout=20000)
                    if page.locator("#result-dialog").is_visible():
                        break
                    page.locator("#pass-button").click()
                expect(page.locator("#result-dialog")).to_be_visible(timeout=20000)
                if language == "en":
                    assert page.locator("#result-title").inner_text() in {"Victory!", "Defeat", "Draw"}
                page.locator("#result-continue").click()
                page.locator("#ready-button").click()
                expect(page.locator("#mulligan-dialog")).to_be_visible()
                assert not online_requests, online_requests
                assert not web_sockets, web_sockets
                assert not app.state.rooms.rooms
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=5)

    print("Local worker started, played a match offline and began a rematch without opening a server room.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default="msedge")
    parser.add_argument("--language", choices=("ru", "en"), default="ru")
    args = parser.parse_args()
    run(args.browser, args.language)
