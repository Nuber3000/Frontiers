"""Check weather placement, animation, clearing and unobstructed card controls."""

import argparse
import asyncio
from pathlib import Path
import socket
import threading
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from frontiers.app import create_app
from frontiers.cards import CombatRow as Row
from test_engine import fixture, put


FINGERPRINT = """() => {
  const canvas=document.querySelector('#weather-effects');
  const row=document.querySelector('.combat-row.weathered .row-cards').getBoundingClientRect();
  const ratio=canvas.width/innerWidth;
  const pixels=canvas.getContext('2d').getImageData(Math.ceil(row.left*ratio), Math.ceil(row.top*ratio),
    Math.floor(row.width*ratio)-1, Math.floor(row.height*ratio)-1).data;
  let hash=2166136261;
  for(let i=0;i<pixels.length;i+=7) hash=Math.imul(hash^pixels[i],16777619);
  return hash>>>0;
}"""

MEAN_ALPHA = """() => {
  const c=document.querySelector('#weather-effects'),ratio=c.width/innerWidth;
  const r=document.querySelector('.combat-row.weathered .row-cards').getBoundingClientRect();
  const d=c.getContext('2d').getImageData(Math.ceil(r.left*ratio),Math.ceil(r.top*ratio),
    Math.floor(r.width*ratio)-1,Math.floor(r.height*ratio)-1).data;
  let sum=0;for(let i=3;i<d.length;i+=4)sum+=d[i];return sum/(d.length/4);
}"""


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
                page = browser.new_page(locale="ru-RU", viewport={"width": 1440, "height": 900})
                other = browser.new_page(locale="ru-RU", viewport={"width": 1366, "height": 768})
                page.add_init_script("localStorage.setItem('frontiers.sound',JSON.stringify({enabled:false,volume:.25}))")
                other.add_init_script("localStorage.setItem('frontiers.sound',JSON.stringify({enabled:false,volume:.25}))")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                other.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{port}"
                code = page.request.post(base + "/api/rooms", data={"name": "Alex"}).json()["code"]
                room = app.state.rooms.rooms[code]
                other.request.post(base + f"/api/rooms/{code}/join", data={"name": "Friend"})
                room.game = fixture(["frost", "fog", "rain", "storm", "frost", "frost", "decoy", "spy_scribe"]
                                    + ["clear"] * 6 + ["knight"] * 4, ["knight"])
                room.game.players[1].passed = True
                for side in (0, 1):
                    for key, row in (("knight", Row.MELEE), ("veteran", Row.MELEE),
                                     ("scout", Row.RANGED), ("crossbow", Row.RANGED),
                                     ("ballista", Row.SIEGE), ("trebuchet", Row.SIEGE)):
                        put(room.game, side, key, row)
                put(room.game, 0, "regent", Row.MELEE)
                original = [room.game.strengths(side) for side in (0, 1)]
                page.goto(base + f"/?room={code}")
                other.goto(base + f"/?room={code}")
                expect(page.locator("#pass-button")).to_be_enabled()
                expect(page.locator("#weather-effects")).to_be_hidden()
                page.evaluate("window.originalWeatherCanvas=document.querySelector('#weather-effects')")

                def play(key):
                    previous = int(page.locator("body").get_attribute("data-game-version"))
                    page.locator(f'#hand [data-card-key="{key}"]').first.click()
                    page.locator("#selection-info .primary").click()
                    page.wait_for_function("v => Number(document.body.dataset.gameVersion)>v", arg=previous)

                if output:
                    output.mkdir(parents=True, exist_ok=True)
                for kind, rows in (("frost", {"melee"}), ("fog", {"ranged"}), ("rain", {"siege"}),
                                   ("storm", {"ranged", "siege"})):
                    play(kind)
                    expect(page.locator("#weather-effects")).to_be_visible()
                    affected = page.locator(f'.combat-row[data-weather~="{kind}"]')
                    expect(affected).to_have_count(len(rows) * 2)
                    assert set(affected.evaluate_all("es=>es.map(e=>e.dataset.row)")) == rows
                    page.wait_for_timeout(140)
                    early_alpha = page.evaluate(MEAN_ALPHA)
                    page.wait_for_timeout(700)
                    assert page.evaluate(MEAN_ALPHA) > early_alpha * 1.3, kind + " appeared abruptly"
                    first = page.evaluate(FINGERPRINT)
                    page.wait_for_timeout(220)
                    assert page.evaluate(FINGERPRINT) != first, kind + " is not animated"
                    assert page.locator("#weather-effects").evaluate("e=>getComputedStyle(e).pointerEvents") == "none"
                    # Both score medallions and boost slots stay outside the painted strip.
                    assert page.evaluate("""() => {
                      const c=document.querySelector('#weather-effects'), ratio=c.width/innerWidth;
                      return [...document.querySelectorAll('.combat-row.weathered .row-info, .combat-row.weathered .row-special')].every(e=>{
                        const r=e.getBoundingClientRect();
                        const d=c.getContext('2d').getImageData(Math.ceil(r.left*ratio),Math.ceil(r.top*ratio),
                          Math.floor(r.width*ratio)-1,Math.floor(r.height*ratio)-1).data;
                        return !d.some((v,i)=>i%4===3&&v>0);
                      });
                    }""")
                    page.locator('#hand [data-card-key="knight"]').first.click()
                    expect(page.locator("#hand .selected")).to_have_count(1)
                    if kind == "frost":
                        wet_target = page.locator('.combat-row.own.weathered.droppable .row-cards')
                        assert wet_target.evaluate("e=>getComputedStyle(e).borderTopColor") == "rgb(230, 195, 108)"
                    assert page.evaluate("originalWeatherCanvas===document.querySelector('#weather-effects')")
                    if output:
                        page.screenshot(path=str(output / f"weather-{kind}.png"))
                    if kind == "storm":
                        page.set_viewport_size({"width": 390, "height": 640})
                        page.wait_for_function("() => document.querySelector('#weather-effects').width === Math.ceil(innerWidth*Math.min(devicePixelRatio||1,1.25))")
                        expect(page.locator("#hand")).to_be_visible()
                        expect(affected).to_have_count(4)
                        if output:
                            page.screenshot(path=str(output / "weather-storm-mobile.png"))
                        page.set_viewport_size({"width": 1440, "height": 900})
                        page.emulate_media(reduced_motion="reduce")
                        page.wait_for_timeout(200)
                        still = page.evaluate(FINGERPRINT)
                        page.wait_for_timeout(200)
                        assert page.evaluate(FINGERPRINT) == still, "Reduced-motion weather keeps moving"
                        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
                        expect(page.locator("#weather-effects")).to_be_hidden()
                        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
                        expect(page.locator("#weather-effects")).to_be_visible()
                        page.emulate_media(reduced_motion="no-preference")
                    play("clear")
                    expect(page.locator(".combat-row.weathered")).to_have_count(0)
                    expect(page.locator('#weather-effects[data-clearing="true"]')).to_be_visible()
                    expect(other.locator('#weather-effects[data-clearing="true"]')).to_be_visible(timeout=5000)
                    if output and kind == "storm":
                        page.screenshot(path=str(output / "clear-skies-rays.png"))
                        other.screenshot(path=str(output / "clear-skies-opponent.png"))
                    expect(page.locator("#weather-effects")).to_be_hidden(timeout=5000)
                    expect(other.locator("#weather-effects")).to_be_hidden(timeout=5000)
                    assert [room.game.strengths(side) for side in (0, 1)] == original

                # Existing cards choose the highlighted row, including keyboard activation.
                play("frost")
                own_row = page.locator('.combat-row.own[data-row="melee"] .row-cards')
                for keyboard in (False, True):
                    version = int(page.locator("body").get_attribute("data-game-version"))
                    before = len(room.game.players[0].board)
                    page.locator('#hand [data-card-key="knight"]').first.click()
                    target = own_row.locator('[data-card-key="regent"]')
                    if keyboard:
                        target.focus()
                        page.keyboard.press("Enter")
                    else:
                        target.click()
                    page.wait_for_function("v=>Number(document.body.dataset.gameVersion)>v", arg=version)
                    assert room.game.version == version + 1, "One activation sent multiple moves"
                    assert len(room.game.players[0].board) == before + 1
                    expect(page.locator("#info-dialog")).to_be_hidden()

                # Spies place onto the enemy row when clicking its existing card.
                version = room.game.version
                page.locator('#hand [data-card-key="spy_scribe"]').click()
                page.locator('.combat-row.enemy.droppable .row-cards .card').first.click()
                page.wait_for_function("v=>Number(document.body.dataset.gameVersion)>v", arg=version)
                assert any(card.card.key == "spy_scribe" for card in room.game.players[1].board)
                expect(page.locator("#info-dialog")).to_be_hidden()

                # Decoy still targets a specific unit rather than selecting the whole row.
                version = room.game.version
                returned = own_row.locator('[data-card-key="veteran"]').get_attribute("data-card-id")
                page.locator('#hand [data-card-key="decoy"]').click()
                own_row.locator('[data-card-key="veteran"]').click()
                page.wait_for_function("v=>Number(document.body.dataset.gameVersion)>v", arg=version)
                assert any(card.id == returned for card in room.game.players[0].hand)
                expect(page.locator("#info-dialog")).to_be_hidden()
                own_row.locator('[data-card-key="regent"]').click()
                expect(page.locator("#info-dialog")).to_be_visible()
                page.locator("#close-info").click()
                other.wait_for_function("v=>Number(document.body.dataset.gameVersion)===v", arg=room.game.version)
                expect(other.locator("#opponent-play")).to_have_count(0, timeout=10000)
                page.locator("#leader-button").click()
                page.locator("#leader-apply").click()
                expect(page.locator('#weather-effects[data-clearing="true"]')).to_be_visible()
                expect(other.locator('#weather-effects[data-clearing="true"]')).to_be_visible(timeout=5000)
                # A newer weather card cancels old sunlight rather than washing out the new effect.
                play("frost")
                expect(page.locator("#weather-effects[data-clearing]")).to_have_count(0)
                expect(page.locator('.combat-row[data-weather="frost"]')).to_have_count(2)
                page.emulate_media(reduced_motion="reduce")
                play("clear")
                expect(page.locator("#weather-effects")).to_be_hidden()
                expect(page.locator("#weather-effects[data-clearing]")).to_have_count(0)
                page.emulate_media(reduced_motion="no-preference")
                play("clear")  # The light effect also works when no weather is present.
                expect(page.locator('#weather-effects[data-clearing="true"]')).to_be_visible()
                page.emulate_media(reduced_motion="reduce")
                expect(page.locator("#weather-effects")).to_be_hidden()
                page.reload()
                expect(page.locator("#hand")).to_be_visible()
                expect(page.locator("#weather-effects[data-clearing]")).to_have_count(0)
                page.locator("#leave-view").click()
                expect(page.locator("#weather-effects")).to_be_hidden()
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Weather fade-in, Clear Skies/Sun on both clients, interrupted light, reduced motion, clipping and card placement passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    run(parser.parse_args().output)
