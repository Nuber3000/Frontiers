"""Leader inspection is always available; only legal moves can apply an ability."""

import argparse
import asyncio
from pathlib import Path
import socket
import threading
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from frontiers.app import create_app
from test_engine import fixture


def run(output):
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
                first = browser.new_page(locale="ru-RU", viewport={"width": 1440, "height": 900})
                second = browser.new_page(locale="ru-RU", viewport={"width": 1366, "height": 768})
                errors = []
                for page in (first, second):
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.add_init_script("localStorage.setItem('frontiers.sound',JSON.stringify({enabled:false,volume:.25}))")
                second.add_init_script("localStorage.setItem('frontiers.language','en')")
                base = f"http://127.0.0.1:{port}"
                code = first.request.post(base + "/api/rooms", data={"name": "Alex"}).json()["code"]
                second.request.post(base + f"/api/rooms/{code}/join", data={"name": "Friend"})
                room = app.state.rooms.rooms[code]

                first.goto(base + f"/?room={code}")
                expect(first.locator("#lobby-leader")).to_be_visible()
                catalog = first.request.get(base + "/api/catalog").json()
                for faction, key in (("burgundy", "academy"), ("skone", "skone_storm"),
                                     ("shiron", "shiron_rain"), ("ellifarn", "ellifarn_logistics")):
                    first.locator("#faction-select").select_option(faction)
                    first.locator("#leader-select").select_option(key)
                    first.locator("#lobby-leader").click()
                    expect(first.locator("#info-dialog")).to_be_visible()
                    expect(first.locator("#info-content h2")).to_have_text(catalog["leaders"][key]["name"])
                    expect(first.locator("#info-content .leader-detail-card")).to_have_attribute("data-leader", key)
                    expect(first.locator("#info-content .leader-detail-card")).to_have_attribute("data-faction", faction)
                    first.locator("#info-content h2").click()
                    expect(first.locator("#info-dialog")).to_be_visible()
                    if output and faction == "skone":
                        output.mkdir(parents=True, exist_ok=True)
                        first.screenshot(path=str(output / "lobby-leader-description.png"))
                    first.mouse.click(5, 5)
                    expect(first.locator("#info-dialog")).to_be_hidden()
                    expect(first.locator("#room")).to_be_visible()
                first.locator("#collection .card").first.click()
                expect(first.locator("#info-dialog")).to_be_visible()
                # Selecting text outward must not be mistaken for clicking the backdrop.
                heading = first.locator("#info-content h2").bounding_box()
                first.mouse.move(heading["x"] + 8, heading["y"] + 8)
                first.mouse.down()
                first.mouse.move(5, 5, steps=8)
                first.mouse.up()
                expect(first.locator("#info-dialog")).to_be_visible()
                first.mouse.click(5, 5)
                expect(first.locator("#info-dialog")).to_be_hidden()

                def load(game):
                    room.game = game
                    room.changed()
                    for page in (first, second):
                        page.goto(base + f"/?room={code}")
                        expect(page.locator("#leader-button")).to_be_visible()
                        expect(page.locator("#connection")).to_have_class("connection online")

                def inspect(page, selector, apply_hidden=False, apply_disabled=False):
                    page.locator(selector).click()
                    expect(page.locator("#leader-dialog")).to_be_visible()
                    assert page.locator("#leader-rule").inner_text()
                    if apply_hidden:
                        expect(page.locator("#leader-apply")).to_be_hidden()
                    elif apply_disabled:
                        expect(page.locator("#leader-apply")).to_be_disabled()
                    else:
                        expect(page.locator("#leader-apply")).to_be_enabled()

                load(fixture(["knight"], ["knight"], "academy", "fog"))
                inspect(second, "#leader-button", apply_disabled=True)
                second.locator("#leader-cancel").click()
                inspect(first, "#enemy-leader", apply_hidden=True)
                first.mouse.click(5, 5)
                expect(first.locator("#leader-dialog")).to_be_hidden()
                assert room.game.version == 0

                inspect(first, "#leader-button")
                first.locator("#leader-apply").click()
                preview = second.locator('#opponent-play[data-kind="leader"]')
                expect(preview).to_be_visible()
                expect(preview.locator('[data-leader="academy"]')).to_be_visible()
                assert preview.locator(".opponent-leader-rule").inner_text()
                assert preview.locator(".opponent-leader-rule").evaluate("e => e.parentElement.classList.contains('opponent-play-card')"), "Rule text clipped inside the card"
                assert second.locator("body").get_attribute("data-game-version") == "0"
                if output:
                    output.mkdir(parents=True, exist_ok=True)
                    second.wait_for_function("() => Number(getComputedStyle(document.querySelector('.opponent-play-card')).opacity) > .99")
                    second.screenshot(path=str(output / "opponent-leader.png"))

                # A description can be opened during playback and stays open as the turn changes.
                inspect(second, "#leader-button", apply_disabled=True)
                expect(preview).to_have_count(0, timeout=5000)
                expect(second.locator("#leader-dialog")).to_be_visible()
                expect(second.locator("#leader-apply")).to_be_enabled()
                second.locator("#leader-apply").click()
                expect(first.locator('#opponent-play[data-kind="leader"] [data-leader="fog"]')).to_be_visible()
                expect(first.locator("#opponent-play")).to_have_count(0, timeout=5000)
                assert room.game.version == 2
                for page in (first, second):
                    inspect(page, "#leader-button", apply_hidden=True)
                    expect(page.locator("#leader-confirmation-status")).to_have_text("Использован" if page is first else "Used")
                    page.locator("#leader-cancel").click()
                    inspect(page, "#enemy-leader", apply_hidden=True)
                    page.keyboard.press("Escape")
                first.reload()
                expect(first.locator("#leader-button")).to_be_visible()
                expect(first.locator("#opponent-play")).to_have_count(0)

                game = fixture(["knight"], ["knight"], "shiron_nullify", "sun")
                game.players[1].leader_blocked = True
                load(game)
                for page in (first, second):
                    for selector in ("#leader-button", "#enemy-leader"):
                        inspect(page, selector, apply_hidden=True)
                        page.locator("#leader-cancel").click()
                assert room.game.version == 0

                # Both leaders remain accessible on portrait and compact landscape layouts.
                for width, height in ((390, 844), (844, 390)):
                    first.set_viewport_size({"width": width, "height": height})
                    for selector in ("#leader-button", "#enemy-leader"):
                        bounds = first.locator(selector).bounding_box()
                        assert bounds and bounds["height"] > 0 and bounds["y"] + bounds["height"] <= height + 1
                        inspect(first, selector, apply_hidden=True)
                        first.locator("#leader-cancel").click()

                game = fixture(["knight"], ["knight"])
                game.phase = "finished"
                game.winner = 0
                load(game)
                for page in (first, second):
                    expect(page.locator("#result-dialog")).to_be_visible(timeout=5000)
                    page.locator("#result-minimize").click()
                    inspect(page, "#leader-button", apply_hidden=True)
                    page.locator("#leader-cancel").click()
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Lobby leader/card descriptions, outside clicks, text dragging, leader playback and inspection states passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    run(parser.parse_args().output)
