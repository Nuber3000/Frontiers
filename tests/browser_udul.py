"""Two browsers exercise Udul's deck, leaders, private selections and soul counters."""
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
from browser_smoke import assert_game_fits, assert_lobby_fits


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    app = create_app()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", timeout_graceful_shutdown=2))
        loop = asyncio.SelectorEventLoop()
        thread = threading.Thread(target=lambda: loop.run_until_complete(server.serve(sockets=[listener])), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("Test server did not start")
                time.sleep(.05)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge")
                pages = [browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce") for _ in range(2)]
                errors = []
                for page in pages:
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.add_init_script("localStorage.setItem('frontiers.sound',JSON.stringify({enabled:false,volume:0,musicVolume:0}))")
                first, second = pages
                base = f"http://127.0.0.1:{port}"
                first.goto(base)
                expect(first.locator("#faction-backs .hero-card")).to_have_count(5)
                code = first.request.post(base + "/api/rooms", data={"name": "Gaur"}).json()["code"]
                second.request.post(base + f"/api/rooms/{code}/join", data={"name": "Friend"})
                room = app.state.rooms.rooms[code]
                for page in pages:
                    page.goto(base + f"/?room={code}")
                    expect(page.locator("#connection.online")).to_be_visible()
                first.locator("#faction-select").select_option("udul")
                expect(first.locator("#leader-select option")).to_have_count(5)
                expect(first.locator('#collection [data-card-key="decoy"], #deck-cards [data-card-key="decoy"]')).to_have_count(0)
                expect(first.locator('#deck-cards [data-card-key="scorch"]').locator('..').locator('.card-adjust span')).to_have_text("×4")
                expect(first.locator('#deck-cards [data-card-key="udul_portal"]').locator('..').locator('.card-adjust span')).to_have_text("×3")
                assert_lobby_fits(first)
                first.screenshot(path=str(output / "udul-lobby.png"))
                first.locator("#language-button").click()
                expect(first.locator("#faction-name")).to_have_text("Udul Sureg")
                first.locator("#language-button").click()
                # Four Scorches must also survive local custom-deck validation.
                assert first.evaluate("""async () => {
                  const c=await (await fetch('/api/catalog')).json(), p=new FrontiersProfile(c);
                  const saved=p.saveDeck('Horde',{faction:'udul',leader:'udul_rite',cards:c.decks.world_horde.cards});
                  return p.decks().some(d=>d.id===saved.id);
                }""")

                def load(game):
                    for page in pages:
                        page.evaluate("document.querySelector('#leave-view').click()")
                    async def install():
                        async with room.lock:
                            room.game = game
                            room.changed()
                    asyncio.run_coroutine_threadsafe(install(), loop).result(5)
                    for page in pages:
                        page.goto(base + f"/?room={code}")
                        expect(page.locator("#connection.online")).to_be_visible()
                        expect(page.locator("#leader-button")).to_be_visible()

                game = fixture(["udul_mauler", "udul_engine", "udul_horde"], ["knight"], "udul_rite")
                put(game, 0, "udul_hunters", Row.RANGED)
                put(game, 1, "knight")
                load(game)
                first.wait_for_function("""() => [...document.querySelectorAll('#arena .card .card-art')]
                  .every(art => art.querySelector('canvas.card-art-image'))""")
                for selector in ('#hand [data-card-key="udul_horde"]', '#leader-button'):
                    result = first.evaluate("""selector => new Promise(resolve => {
                      document.querySelector(selector).click();
                      requestAnimationFrame(() => resolve([...document.querySelectorAll('#arena .card .card-art')]
                        .filter(art => !art.querySelector('canvas.card-art-image')).map(art => art.className)));
                    })""", selector)
                    assert not result, (selector, result)
                first.locator("#leader-cancel").click()
                print("Hand selection and leader preview retain smooth artwork in the first displayed frame.")

                first.emulate_media(reduced_motion="no-preference")
                game = fixture(["udul_mauler", "udul_engine", "udul_horde"], ["knight", "veteran"], "udul_rite", "sun")
                game.turn = 1
                put(game, 0, "udul_hunters", Row.RANGED)
                put(game, 1, "knight")
                load(game)
                first.wait_for_function("""() => [...document.querySelectorAll('#arena .card .card-art')]
                  .every(art => art.querySelector('canvas.card-art-image'))""")
                first.evaluate("""() => {
                  window.unsmoothedOpponentFrames = [];
                  window.retainedTableCards = [...document.querySelectorAll('#arena .card[data-card-id]')]
                    .map(card => ({card, id:card.dataset.cardId, canvas:card.querySelector('canvas.card-art-image')}));
                  window.flightPixelSizes = [];
                  Object.defineProperty(document, 'visibilityState', {configurable:true, value:'visible'});
                  window.artObserver = new MutationObserver(() => {
                    requestAnimationFrame(() => setTimeout(() => {
                      const missing = [...document.querySelectorAll('#arena .card .card-art, #opponent-play .card .card-art')]
                        .filter(art => getComputedStyle(art).visibility === 'visible'
                          && !art.querySelector('canvas.card-art-image'));
                      const flying = document.querySelector('#opponent-play[data-stage="flight"] canvas.card-art-image');
                      if (flying) {
                        const rect = flying.getBoundingClientRect();
                        window.flightPixelSizes.push([flying.width, flying.height,
                          rect.width * devicePixelRatio, rect.height * devicePixelRatio]);
                      }
                      if (missing.length) window.unsmoothedOpponentFrames.push(missing.map(art => ({
                        art:art.className, parent:art.closest('#opponent-play') ? 'preview' : 'table',
                        size:getComputedStyle(art).backgroundSize, stage:document.querySelector('#opponent-play')?.dataset.stage,
                        width:art.clientWidth, children:art.innerHTML,
                      })));
                    }, 0));
                  });
                  window.artObserver.observe(document.body, {childList:true,subtree:true,attributes:true});
                }""")
                hand_art = first.locator('#hand [data-card-key="udul_mauler"] .card-art')
                box = hand_art.bounding_box()
                clip = {"x": box["x"] + 25, "y": box["y"] + 35, "width": 60, "height": 65}
                before_pixels = first.screenshot(clip=clip)
                second.locator('#hand [data-card-key="veteran"]').click()
                second.locator('#selection-info .primary').click()
                first.locator('#opponent-play[data-stage="reveal"]').wait_for()
                assert first.screenshot(clip=clip) == before_pixels, "A stationary card changed during the opponent's move"
                expect(first.locator('#hand [data-card-key="udul_mauler"]')).to_be_disabled()
                first.wait_for_function("() => document.body.dataset.gameVersion === '1'")
                expect(first.locator("#opponent-play")).to_have_count(0)
                assert first.evaluate("""() => window.retainedTableCards.every(({card,id,canvas}) =>
                  document.querySelector('#arena [data-card-id="' + id + '"]') === card
                  && card.querySelector('canvas.card-art-image') === canvas)""")
                sizes = first.evaluate("window.flightPixelSizes")
                assert sizes and all(abs(width - shown_width) <= 1 and abs(height - shown_height) <= 1
                                     for width, height, shown_width, shown_height in sizes), sizes
                first.evaluate("window.artObserver.disconnect()")
                failures = first.evaluate("window.unsmoothedOpponentFrames")
                assert not failures, failures
                print("Opponent reveal, flight and placement preserve smooth table artwork.")
                first.emulate_media(reduced_motion="reduce")

                def ability():
                    first.locator("#leader-button").click()
                    first.locator("#leader-apply").click()
                    expect(first.locator("#choice-dialog")).to_be_visible()

                def choose(key, row=None):
                    card = first.locator(f'#choice-cards [data-card-key="{key}"]').first
                    item = card.locator('..')
                    target = item.locator(f'button.primary[data-choice-row="{row}"]') if row else item.locator('button.primary').first
                    version = room.game.version
                    target.click()
                    first.wait_for_function("v=>Number(document.body.dataset.gameVersion)>v", arg=version)

                for leader, deck in (("udul_rite", ["frost", "clear"]),
                                     ("udul_sacrifice", ["udul_hero_warlord"]),
                                     ("udul_necromancy", []), ("udul_spirit", ["horn"]),
                                     ("udul_souls", ["udul_hero_huntress"])):
                    game = fixture(["udul_mauler", "udul_engine", "udul_horde"], ["knight"], leader)
                    game.players[0].deck = [game._new_card(key) for key in deck]
                    game.players[0].discard = [game._new_card(key) for key in ("udul_healer", "udul_mauler")]
                    game.players[0].souls = 3
                    load(game)
                    assert_game_fits(first)
                    ability()
                    first.screenshot(path=str(output / f"{leader}-choice.png"))
                    if leader == "udul_rite":
                        choose("frost")
                        assert room.game.weather[0].key == "frost"
                    elif leader == "udul_sacrifice":
                        choose("udul_mauler")
                        choose("udul_engine")
                        choose("udul_hero_warlord")
                    elif leader == "udul_necromancy":
                        choose("udul_healer")
                        choose("udul_mauler")
                    elif leader == "udul_spirit":
                        choose("horn", "ranged")
                        expect(first.locator('.combat-row[data-side="own"][data-row="ranged"] .row-special .art-udul_horn')).to_be_visible()
                    else:
                        choose("udul_hero_huntress")
                        expect(first.locator("#leader-button .soul-counter")).to_have_text("Души: 0 / 3")
                        expect(second.locator("#enemy-leader .soul-counter")).to_have_text("Души: 0 / 3")
                        badge = first.locator("#leader-button .soul-counter").bounding_box()
                        leader_box = first.locator("#leader-button").bounding_box()
                        assert leader_box['y'] <= badge['y'] and badge['y']+badge['height'] <= leader_box['y']+leader_box['height']
                    expect(first.locator("#choice-dialog")).to_be_hidden()
                    self_state = first.request.get(base+f"/api/rooms/{code}").json()
                    assert self_state["game"]["turn"] == 1

                game = fixture(["spy_scribe"], ["udul_healer", "udul_mauler"], "sun", "udul_souls")
                game.players[1].discard = [game._new_card("udul_mauler")]
                spy = game.players[0].hand[0]
                load(game)
                for page, pile in ((first, "enemy-discard"), (second, "own-discard")):
                    page.evaluate("""({id, pile}) => {
                      const discard = document.getElementById(pile);
                      const burnSelector = `.scorch-burn[data-burn-id="${id}"]`;
                      const spySelector = `#info-content [data-card-id="${id}"]`;
                      Object.defineProperty(document, 'visibilityState', {configurable: true, value: 'visible'});
                      window.spyDiscardBeforeBurn = null;
                      const observer = new MutationObserver(() => {
                        const burn = document.querySelector(burnSelector);
                        if (!burn || !burn.firstElementChild.getAnimations().length) return;
                        observer.disconnect();
                        window.spyBurnVisibility = getComputedStyle(burn.firstElementChild).visibility;
                        window.spyBurnRow = burn.closest(".combat-row").dataset.side;
                        discard.click();
                        window.spyDiscardBeforeBurn = [
                          discard.querySelector('small').textContent,
                          !!discard.querySelector('.art-spy_scribe'),
                          !!document.querySelector(spySelector),
                        ];
                      });
                      observer.observe(document.body, {childList: true, subtree: true, attributes: true});
                    }""", {"id": spy.id, "pile": pile})
                first.locator('#hand [data-card-key="spy_scribe"]').click()
                first.locator('#selection-info .primary').click()
                for page, pile in ((first, "enemy-discard"), (second, "own-discard")):
                    page.wait_for_function("() => window.spyDiscardBeforeBurn !== null")
                    assert page.evaluate("window.spyBurnVisibility") == "visible"
                    assert page.evaluate("window.spyBurnRow") == ("own" if pile == "own-discard" else "enemy")
                    assert page.evaluate("window.spyDiscardBeforeBurn") == ["Сброс · 1", False, False]
                    expect(page.locator(f"#{pile} small")).to_have_text("Сброс · 2")
                    expect(page.locator(f"#{pile} .art-spy_scribe")).to_have_count(1)
                    expect(page.locator(f'#info-content [data-card-id="{spy.id}"]')).to_be_visible()
                    expect(page.locator(f'.scorch-burn[data-burn-id="{spy.id}"]')).to_have_count(0)
                    page.locator("#close-info").click()

                game = fixture(["udul_portal", "scorch"], ["knight"], "udul_souls")
                game.players[0].deck = [game._new_card(key) for key in ("udul_mauler", "udul_hero_huntress")]
                load(game)
                first.locator('#hand [data-card-key="udul_portal"]').click()
                first.locator('#selection-info .primary').click()
                expect(first.locator('.combat-row[data-side="own"] .row-cards .card')).to_have_count(2)
                first.screenshot(path=str(output / "udul-portal-board.png"))
                first.set_viewport_size({"width": 1366, "height": 768})
                assert_game_fits(first)
                first.screenshot(path=str(output / "udul-board-1366.png"))
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Udul lobby, four Scorches, saved decks, all leader choices, souls on both clients and Portal passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/browser/udul"))
    run(parser.parse_args().output)
