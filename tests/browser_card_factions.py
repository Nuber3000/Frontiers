"""Two players must see the same faction ribbons after a spy is exchanged for Decoy."""

import asyncio
import socket
import threading
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from frontiers.app import create_app
from test_engine import fixture


def run():
    app = create_app()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
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
                    raise RuntimeError("Test server did not start")
                time.sleep(.05)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge")
                pages = [browser.new_page(viewport={"width": 1366, "height": 768}, reduced_motion="reduce") for _ in range(2)]
                errors = []
                for page in pages:
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.add_init_script("localStorage.setItem('frontiers.sound',JSON.stringify({enabled:false,volume:.25}))")
                first, second = pages
                base = f"http://127.0.0.1:{port}"
                for faction, leader in (("skone", "skone_storm"), ("shiron", "shiron_rain"),
                                        ("ellifarn", "ellifarn_trade"), ("burgundy", "sun")):
                    code = first.request.post(base + "/api/rooms", data={"name": "Spy"}).json()["code"]
                    second.request.post(base + f"/api/rooms/{code}/join", data={"name": "Decoy"})
                    room = app.state.rooms.rooms[code]
                    room.game = fixture(["spy_scribe", "knight"], ["decoy", "knight"],
                                        "sun" if faction != "burgundy" else "skone_storm", leader)
                    for page in pages:
                        page.goto(base + f"/?room={code}")
                        expect(page.locator("#hand .card")).to_have_count(2)
                    spy_id = room.game.players[0].hand[0].id
                    first.locator('#hand [data-card-key="spy_scribe"]').click()
                    first.locator("#selection-info .primary").click()
                    own_spy = second.locator(f'#own-rows [data-card-id="{spy_id}"]')
                    expect(own_spy).to_have_attribute("data-faction", "burgundy")
                    second.locator('#hand [data-card-key="decoy"]').click()
                    own_spy.click()
                    for page in pages:
                        target = page.locator('#arena .row-cards [data-card-key="decoy"]')
                        expect(target).to_have_attribute("data-faction", faction)
                        if faction == "skone":
                            expect(target.locator(".card-ribbon")).to_have_class("card-ribbon valknut-mark")
                        ribbon = target.locator(".card-ribbon").evaluate("e=>getComputedStyle(e).backgroundImage")
                        target.click()
                        detail = page.locator('#info-dialog [data-card-key="decoy"]')
                        expect(detail).to_have_attribute("data-faction", faction)
                        assert detail.locator(".card-ribbon").evaluate("e=>getComputedStyle(e).backgroundImage") == ribbon
                        page.mouse.click(5, 5)
                        expect(page.locator("#info-dialog")).to_be_hidden()
                    expect(second.locator(f'#hand [data-card-id="{spy_id}"]')).to_have_attribute("data-faction", "burgundy")
                    assert room.game.version == 2
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Decoy ribbons match for both players and descriptions in all four factions; captured spies keep their original faction.")


if __name__ == "__main__":
    run()
