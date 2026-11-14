"""Check scrolling real hand/row cards without accidentally selecting or playing."""

import asyncio
import socket
import threading
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from frontiers.app import create_app
from test_engine import fixture, put


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
                page = browser.new_page(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{port}"
                created = page.request.post(f"{base}/api/rooms", data={"name": "Alex"}).json()
                room = app.state.rooms.rooms[created["code"]]
                room.join("guest", "Friend")
                room.game = fixture(["knight"] * 24, ["knight"])
                for side in (0, 1):
                    for _ in range(24):
                        put(room.game, side, "knight")
                page.goto(f"{base}/?room={room.code}")
                expect(page.locator("#hand .card")).to_have_count(24)
                expect(page.locator("#pass-button")).to_be_enabled()
                version = page.locator("body").get_attribute("data-game-version")
                hand = page.locator("#hand")
                own_row = page.locator('.combat-row.own[data-row="melee"] .row-cards')
                enemy_row = page.locator('.combat-row.enemy[data-row="melee"] .row-cards')

                for element in (hand, own_row, enemy_row):
                    assert element.evaluate("e => e.scrollWidth > e.clientWidth"), "Fixture should overflow"
                    assert element.evaluate("e => getComputedStyle(e).scrollbarWidth") == "none"
                    assert element.evaluate("e => getComputedStyle(e, '::-webkit-scrollbar').display") == "none"
                    element.hover()
                    page.mouse.wheel(0, 200)
                    page.wait_for_function("e => e.scrollLeft > 100", arg=element.element_handle())
                    page.mouse.wheel(0, -200)
                    page.wait_for_function("e => e.scrollLeft < 1", arg=element.element_handle())

                def drag(element):
                    bounds = element.bounding_box()
                    x, y = bounds["x"] + 150, bounds["y"] + bounds["height"] / 2
                    page.mouse.move(x, y)
                    page.mouse.down()
                    page.mouse.move(x - 120, y, steps=12)
                    page.mouse.up()
                    assert element.evaluate("e => e.scrollLeft") > 100
                    expect(page.locator("#info-dialog")).to_be_hidden()
                    assert page.locator("body").get_attribute("data-game-version") == version

                drag(hand)
                expect(page.locator("#hand .selected")).to_have_count(0)
                hand.evaluate("e => e.scrollLeft = 0")
                page.locator("#hand .card").nth(1).click()
                expect(page.locator("#hand .selected")).to_have_count(1)
                drag(own_row)  # A selected card makes the entire row a play target.
                drag(enemy_row)
                expect(page.locator("#hand .selected")).to_have_count(1)
                before = own_row.evaluate("e => e.scrollLeft")
                page.locator("#hand .card").nth(2).click()
                assert own_row.evaluate("e => e.scrollLeft") == before, "Rerender reset the row position"
                page.locator("#hand .selected").click()  # Inspect only after cancelling placement.
                own_row.evaluate("e => e.scrollLeft = 0")
                own_row.locator(".card").first.click()
                expect(page.locator("#info-dialog")).to_be_visible()
                page.locator("#close-info").click()
                assert hand.evaluate("""e => e.dispatchEvent(new WheelEvent('wheel',
                    {deltaY:100, ctrlKey:true, bubbles:true, cancelable:true}))"""), "Zoom gesture intercepted"
                empty = page.locator('.combat-row.own[data-row="siege"] .row-cards')
                assert empty.evaluate("""e => e.dispatchEvent(new WheelEvent('wheel',
                    {deltaY:100, bubbles:true, cancelable:true}))"""), "Empty row intercepted scrolling"
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Hidden scrollbars, wheel, mouse drag, normal clicks and scroll restoration passed.")


if __name__ == "__main__":
    run()
