"""Offer training at match entry, with no side effects until the user decides."""
import asyncio
import socket
import threading
import time

import uvicorn
from playwright.sync_api import expect, sync_playwright

from frontiers.app import create_app


def run():
    app = create_app()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", timeout_graceful_shutdown=2))
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
                    raise RuntimeError("Offer test server did not start")
                time.sleep(.05)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge")
                errors = []
                for action in ("find-match", "create-room", "play-bot"):
                    context = browser.new_context(locale="ru-RU")
                    page = context.new_page()
                    requests, sockets = [], []
                    page.on("request", lambda request: requests.append(request.url) if request.method == "POST" else None)
                    page.on("websocket", lambda ws: sockets.append(ws.url))
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url)
                    expect(page.locator("#tutorial-button")).to_be_enabled()
                    expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                    # Even before a name is entered, the first attempted action offers training.
                    page.locator("#" + action).click()
                    expect(page.locator("#tutorial-offer-dialog")).to_be_visible()
                    assert not requests and not sockets
                    page.keyboard.press("Escape")
                    expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                    assert not requests
                    page.locator("#player-name").fill("Новичок")
                    page.locator("#" + action).click()
                    expect(page.locator("#tutorial-offer-dialog")).to_be_visible()
                    assert not requests
                    page.locator("#tutorial-offer-later").click()
                    expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                    if action == "find-match":
                        expect(page.locator("#matchmaking-status")).to_be_visible()
                        assert sum(endpoint.endswith("/api/matchmaking") for endpoint in requests) == 1, requests
                        page.locator("#find-match").click()
                        expect(page.locator("#matchmaking-status")).to_be_hidden()
                    elif action == "create-room":
                        expect(page.locator("#connection.online")).to_be_visible()
                        assert sum(endpoint.endswith("/api/rooms") for endpoint in requests) == 1, requests
                        page.reload()
                        expect(page.locator("#connection.online")).to_be_visible()
                        expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                        page.locator("#leave-view").click()
                    else:
                        expect(page.locator("#bot-setup-dialog")).to_be_visible()
                        assert not requests
                        page.locator("#bot-setup-cancel").click()
                    # No match has finished: every subsequent attempt still offers training.
                    page.locator("#" + action).click()
                    expect(page.locator("#tutorial-offer-dialog")).to_be_visible()
                    before = len(requests)
                    page.locator("#tutorial-offer-start").click()
                    expect(page.locator("#deck-tutorial-coach")).to_be_visible()
                    assert len(requests) == before, requests
                    page.locator("#deck-tutorial-exit").click()
                    expect(page.locator("#landing")).to_be_visible()
                    context.close()

                context = browser.new_context(locale="en-US")
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url)
                expect(page.locator("#tutorial-button")).to_be_enabled()
                page.locator("#player-name").fill("Experienced")
                page.evaluate("""localStorage.setItem('frontiers.profile.v1.history', JSON.stringify([
                    {id:'one-finished-match',finishedAt:Date.now(),outcome:'defeat',
                     players:[{name:'A',faction:'burgundy'},{name:'B',faction:'burgundy'}],rounds:[]}
                ]))""")
                page.locator("#play-bot").click()
                expect(page.locator("#bot-setup-dialog")).to_be_visible()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                page.locator("#bot-setup-cancel").click()
                page.locator("#find-match").click()
                expect(page.locator("#matchmaking-status")).to_be_visible()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                page.locator("#find-match").click()
                expect(page.locator("#matchmaking-status")).to_be_hidden()
                page.locator("#create-room").click()
                expect(page.locator("#connection.online")).to_be_visible()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                page.locator("#leave-view").click()
                page.evaluate("localStorage.removeItem('frontiers.profile.v1.history')")
                page.locator("#play-bot").click()
                expect(page.locator("#tutorial-offer-dialog")).to_be_visible()
                expect(page.locator("#tutorial-offer-start")).to_have_text("Start tutorial")
                context.close()
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Search, room and bot offers passed: no startup prompt or premature commands, Later resumes once, Escape cancels, training replaces entry, and one finished match skips the offer.")


if __name__ == "__main__":
    run()
