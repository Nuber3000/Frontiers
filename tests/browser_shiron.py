"""Две настоящие сессии: фракции, пять способностей Широна и скрытая информация.

Фикстуры меняются только в памяти тестового сервера; отладочного API нет.
"""

import argparse
import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import socket
import threading
import time

from playwright.sync_api import sync_playwright
import uvicorn

from frontiers.app import create_app
from frontiers.catalog import STARTER_DECK
from frontiers.engine import Game
from frontiers.cards import CombatRow as Row
from frontiers.models import PlacedCard
from frontiers.shiron import SHIRON_DECK
from browser_smoke import assert_game_fits, snapshot, wait_version, save_announcement, click_move
from test_engine import fixture, put


ROOT = Path(__file__).resolve().parents[1]


def run(channel, output):
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    app = create_app()
    loop = asyncio.SelectorEventLoop()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', timeout_graceful_shutdown=3))
    thread = threading.Thread(target=lambda: loop.run_until_complete(server.serve()), daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{port}'
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError('Test server did not start')
        time.sleep(.05)
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel=None if channel == 'chromium' else channel)
            contexts = [browser.new_context(viewport={'width': w, 'height': h}) for w, h in [(1440, 1000), (1366, 768)]]
            pages = [context.new_page() for context in contexts]
            for page in pages:
                page.set_default_timeout(15000)
                page.on('pageerror', lambda error: errors.append(str(error)))
            first, second = pages
            try:
                first.goto(url)
                first.locator('#player-name').fill('Император')
                first.locator('#create-room').click()
                first.wait_for_selector('#connection.online')
                code = first.locator('#room-label').inner_text()
                first.locator('#faction-select').select_option('shiron')
                first.locator('#leader-select').select_option('shiron_spy')
                assert first.locator('#deck-cards .card[data-card-key="horn"] .card-art').get_attribute('class').split()[-1] == 'art-shiron_horn'
                assert first.locator('#deck-cards [data-card-key="shiron_spy_hero"] .card-power').inner_text() == '0'
                assert first.locator('#deck-cards [data-card-key="shiron_sorceress"] .ability-seal svg').get_attribute('data-icon') == 'banner'
                for key in ('shiron_amber', 'shiron_ruby'):
                    assert first.locator(f'#deck-cards [data-card-key="{key}"] .ability-seal').get_attribute('data-ability') == 'medic'
                first.screenshot(path=str(output / 'shiron-updated-deck.png'))
                second.goto(f'{url}/?room={code}')
                second.locator('#player-name').fill('Король')
                second.locator('#join-room').click()
                second.wait_for_selector('#connection.online')
                first.locator('#ready-button').click()
                second.locator('#ready-button').click()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='visible')
                    page.locator('#mulligan-button').click()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='hidden')
                    assert_game_fits(page)
                initial = snapshot(first, code)
                assert [player['faction'] for player in initial['game']['players']] == ['shiron', 'burgundy']
                if initial['game']['turn'] == 1:
                    version = initial['game']['version']
                    second.locator('#pass-button').click()
                    wait_version(first, version)

                def leader():
                    version = snapshot(first, code)['game']['version']
                    first.locator('#leader-button').click()
                    first.locator('#leader-dialog').wait_for(state='visible')
                    first.locator('#leader-apply').click()
                    wait_version(first, version)
                    wait_version(second, version)
                    first.locator('#leader-dialog').wait_for(state='hidden')

                leader()
                first.locator('#info-dialog .intel-cards .card').first.wait_for()
                assert first.locator('.intel-cards .card').count() == 3
                assert second.locator('#info-dialog').is_hidden()
                assert 'revealed' not in snapshot(second, code)['game']['players'][0]
                for width, height in [(1440, 1000), (1366, 768), (390, 844), (844, 390)]:
                    first.set_viewport_size({'width':width, 'height':height})
                    assert first.evaluate('''() => {
                      const dialog = document.querySelector('#info-dialog'), box = dialog.getBoundingClientRect();
                      return [...dialog.querySelectorAll('.intel-cards .card')].every(card => {
                        const r = card.getBoundingClientRect();
                        return r.top >= box.top && r.bottom <= box.bottom && r.left >= box.left && r.right <= box.right
                          && Math.abs(r.width / r.height - .61) < .01;
                      }) && box.bottom <= innerHeight + 1 && box.right <= innerWidth + 1;
                    }''')
                    first.screenshot(path=str(output / f'intelligence-{width}x{height}.png'))
                first.set_viewport_size({'width':1440, 'height':1000})
                first.screenshot(path=str(output / 'shiron-intelligence.png'))
                first.keyboard.press('Escape')

                def load(game):
                    for page in pages:
                        page.evaluate("() => document.querySelector('#leave-view').click()")

                    async def install():
                        room = app.state.rooms.rooms[code]
                        async with room.lock:
                            room.game = game
                            room.changed()
                    asyncio.run_coroutine_threadsafe(install(), loop).result(timeout=5)
                    for page in pages:
                        page.goto(f'{url}/?room={code}')
                        page.wait_for_selector('#connection.online', state='attached')
                        page.locator('.combat-row').first.wait_for()

                game = fixture(['shiron_eck'], ['clear', 'knight', 'horn'], 'shiron_spy')
                load(game)
                leader()
                first.locator('#info-dialog .art-clear').wait_for()
                assert first.locator('#info-dialog .art-clear').evaluate("art => getComputedStyle(art).backgroundSize") == '400% 300%'
                assert first.locator('#info-dialog .card.unit .card-art').evaluate("art => getComputedStyle(art).backgroundSize") == 'contain'
                first.screenshot(path=str(output / 'intelligence-no-crop.png'))
                first.keyboard.press('Escape')

                game = fixture(['shiron_eck', 'shiron_marksman'], ['knight'], 'shiron_rain')
                game.players[1].passed = True
                load(game)
                for page in pages:
                    assert page.evaluate('''() => {
                      const text = document.querySelector('.frontier-line > span').getBoundingClientRect();
                      const icon = document.querySelector('.row-medallion').getBoundingClientRect();
                      return Math.abs(text.left + text.width/2 - icon.left - icon.width/2) < 2;
                    }''')
                ids = [card.id for card in game.players[0].hand]
                second.evaluate('''() => {
                  window.seenPreviews = []; const seen = new WeakSet();
                  new MutationObserver(() => {
                    const layer = document.querySelector('#opponent-play');
                    if (layer && !seen.has(layer)) { seen.add(layer); window.seenPreviews.push(layer.querySelector('.card').dataset.cardId); }
                  }).observe(document.body, {childList:true});
                }''')
                click_move(first, {'type':'play', 'card_id':ids[0], 'row':'melee'})
                second.locator('#opponent-play').wait_for()
                second.wait_for_function("() => Number(getComputedStyle(document.querySelector('.opponent-play-card')).opacity) > .99")
                assert second.locator('#enemy-rows .card').count() == 0
                assert second.locator('#pass-button').is_disabled()
                second.screenshot(path=str(output / 'opponent-card-preview.png'))
                wait_version(first, 0)
                click_move(first, {'type':'play', 'card_id':ids[1], 'row':'ranged'})
                wait_version(second, 1)
                second.locator('#opponent-play').wait_for(state='detached')
                assert second.evaluate('window.seenPreviews') == ids
                assert second.locator('#enemy-rows .card').count() == 2
                second.reload()
                second.wait_for_selector('#connection.online')
                assert second.locator('#opponent-play').count() == 0

                game = fixture(['scorch', 'shiron_eck'], ['knight'], 'shiron_rain')
                victim = put(game, 1, 'knight')
                load(game)
                click_move(first, {'type':'play', 'card_id':game.players[0].hand[0].id})
                second.wait_for_selector('#opponent-play[data-stage="burn"]')
                second.locator('#opponent-fire-effects').wait_for(state='visible')
                second.wait_for_function("() => document.querySelector('#opponent-play .card').getAnimations()[0].currentTime > 250")
                assert second.locator(f'#own-rows [data-card-id="{victim.id}"]').count() == 1
                second.screenshot(path=str(output / 'opponent-scorch-preview.png'))
                wait_version(second, 0)
                second.locator('#opponent-play').wait_for(state='detached')
                assert second.locator(f'.scorch-burn[data-burn-id="{victim.id}"]').count() == 1

                game = fixture(['shiron_eck'], ['knight'], 'shiron_rain')
                load(game)
                second.evaluate("() => { Object.defineProperty(document, 'visibilityState', {configurable:true,get:()=> 'hidden'}); document.dispatchEvent(new Event('visibilitychange')); }")
                click_move(first, {'type':'play','card_id':game.players[0].hand[0].id,'row':'melee'})
                second.wait_for_selector('#opponent-play', state='attached')
                first.wait_for_timeout(900)
                assert second.locator('body').get_attribute('data-game-version') == '0'
                second.evaluate("() => { delete document.visibilityState; document.dispatchEvent(new Event('visibilitychange')); }")
                second.locator('#opponent-play').wait_for(state='detached')
                assert second.locator('#enemy-rows .card').count() == 1
                second.emulate_media(reduced_motion='reduce')
                load(fixture(['shiron_eck'], ['knight'], 'shiron_rain'))
                active = snapshot(first, code)['game']
                click_move(first, next(m for m in active['moves'] if m['type']=='play'))
                wait_version(second, 0)
                assert second.locator('#opponent-play').count() == 0
                second.emulate_media(reduced_motion='no-preference')

                game = fixture(['horn', 'shiron_spy_hero'], ['horn'], 'shiron_rain')
                game.players[0].specials.append(PlacedCard(game._new_card('horn'), Row.SIEGE))
                game.players[1].specials.append(PlacedCard(game._new_card('horn'), Row.RANGED))
                game.players[0].discard.append(game._new_card('horn'))
                load(game)
                for page, shiron_side, burgundy_side in ((first, '#own-rows', '#enemy-rows'), (second, '#enemy-rows', '#own-rows')):
                    assert page.locator(shiron_side + ' .row-special .art-shiron_horn').count() == 1
                    assert page.locator(burgundy_side + ' .row-special .art-horn').count() == 1
                assert first.locator('#own-discard .art-shiron_horn').count() == 1
                second.locator('#enemy-rows .row-special .card').click()
                assert second.locator('#info-dialog .art-shiron_horn').count() == 1
                second.keyboard.press('Escape')
                backgrounds = [page.evaluate("() => ['own-deck','enemy-deck'].map(id => getComputedStyle(document.getElementById(id)).backgroundImage)") for page in pages]
                assert backgrounds[0][0] == backgrounds[1][1]
                assert backgrounds[0][1] == backgrounds[1][0]
                assert backgrounds[0][0] != backgrounds[0][1]
                first.screenshot(path=str(output / 'shiron-standards.png'))
                load(fixture(['horn'], ['horn']))
                for page in pages:
                    assert page.locator('#hand .art-horn').count() == 1
                    assert page.locator('#hand .art-shiron_horn').count() == 0
                    own, enemy = page.evaluate("() => ['own-deck','enemy-deck'].map(id => getComputedStyle(document.getElementById(id)).backgroundImage)")
                    assert own == enemy and '18, 38, 60' in own, (own, enemy)
                first.screenshot(path=str(output / 'burgundy-blue-decks.png'))

                game = fixture(['shiron_eck'], ['knight'], 'shiron_levy')
                stolen = game._new_card('crossbow')
                game.players[1].discard = [stolen, game._new_card('champion'), game._new_card('horn')]
                load(game)
                leader()
                first.locator('#choice-dialog').wait_for(state='visible')
                assert first.locator('#choice-cards .card').count() == 1
                assert first.locator('#choice-dialog h2').inner_text() == 'Забрать отряд в руку'
                first.screenshot(path=str(output / 'shiron-levy-choice.png'))
                version = snapshot(first, code)['game']['version']
                first.locator('#choice-cards button.primary').click()
                wait_version(first, version)
                wait_version(second, version)
                first.locator('#choice-dialog').wait_for(state='hidden')
                assert first.locator(f'#hand .card[data-card-id="{stolen.id}"]').count() == 1
                assert stolen.id not in json.dumps(snapshot(second, code))

                game = fixture(['shiron_eck'], ['knight'], 'shiron_hand')
                revived = game._new_card('shiron_spy')
                game.players[0].discard = [revived]
                game.players[0].deck = [game._new_card('shiron_eck') for _ in range(2)]
                load(game)
                leader()
                assert first.locator(f'#enemy-rows .card[data-card-id="{revived.id}"]').count() == 1
                assert len(snapshot(first, code)['game']['players'][0]['hand']) == 3

                game = fixture(['shiron_eck'], ['knight'], 'shiron_rain')
                put(game, 0, 'shiron_scorpion')
                put(game, 1, 'catapult')
                load(game)
                leader()
                result = snapshot(first, code)['game']
                assert [player['score'] for player in result['players']] == [1, 1]
                for page in pages:
                    assert page.locator('.weather-chip').inner_text() == 'Ливень'
                    assert_game_fits(page)
                first.screenshot(path=str(output / 'shiron-vs-burgundy.png'))

                game = Game.create(['Император', 'Король'], [SHIRON_DECK, STARTER_DECK], ['shiron_nullify', 'sun'], seed=5)
                game.phase, game.turn = 'playing', 0
                load(game)
                assert first.locator('#leader-button').is_disabled()
                assert second.locator('#leader-button').is_disabled()
                assert first.locator('#enemy-leader .leader-availability').text_content() == 'Заблокирован'
                assert second.locator('#enemy-leader .leader-availability').text_content() == 'Пассивная способность'
                first.screenshot(path=str(output / 'shiron-passive.png'))

                game = fixture(['shiron_eck'], ['knight'], 'shiron_rain')
                put(game, 0, 'knight')
                put(game, 1, 'knight')
                game.players[1].passed = True
                load(game)
                first.locator('#pass-button').click()
                wait_version(first, 0)
                wait_version(second, 0)
                for page in pages:
                    result = snapshot(page, code)['game']
                    assert result['history'][0]['scores'] == [5, 5]
                    assert result['history'][0]['winner'] == 0
                save_announcement(first, output, 'shiron-tie-win.png', 'round-win')
                assert not errors, errors
                print(json.dumps({'browser':channel, 'mixed_factions':'ok', 'all_five_leaders':'ok', 'private_intelligence':'ok',
                                  'levy_choice':'ok', 'resurrection_spy':'ok', 'tie_win':'ok', 'opponent_preview':'ok',
                                  'queued_plays':'ok', 'preview_burn':'ok', 'intel_proportions':'ok', 'frontier_alignment':'ok', 'js_errors':errors}))
            except Exception:
                for side, page in enumerate(pages):
                    with suppress(Exception):
                        page.screenshot(path=str(output / f'shiron-failure-{side}.png'), full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError('Test server did not stop')
        loop.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', default='msedge' if os.name == 'nt' else 'chromium', choices=['msedge','chrome','chromium'])
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts' / 'browser')
    options = parser.parse_args()
    run(options.browser, options.output)
