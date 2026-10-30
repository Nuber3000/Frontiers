"""Две сессии Сконе: оформление, направленный рог и выборы лекарей в третьем раунде."""

import argparse
import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import random
import socket
import threading
import time

from playwright.sync_api import sync_playwright
import uvicorn

from frontiers.app import create_app
from frontiers.cards import CombatRow as Row
from browser_smoke import assert_game_fits, assert_lobby_fits, snapshot, wait_version, click_move
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
            contexts = [browser.new_context(viewport={'width':1440, 'height':1000}) for _ in range(2)]
            pages = [ctx.new_page() for ctx in contexts]
            for page in pages:
                page.set_default_timeout(15000)
                page.on('pageerror', lambda error: errors.append(str(error)))
            first, second = pages
            try:
                first.goto(url)
                first.locator('#player-name').fill('Конунг')
                first.locator('#create-room').click()
                first.wait_for_selector('#connection.online')
                code = first.locator('#room-label').inner_text()
                first.locator('#faction-select').select_option('skone')
                assert first.locator('#leader-select option').count() == 5
                assert first.locator('.faction-crest .valknut-mark').count() == 1
                assert first.locator('#deck-preset option[value="clans"]').inner_text() == 'Союз северных кланов'
                assert first.locator('#collection .card[data-faction="burgundy"], #collection .card[data-faction="shiron"]').count() == 0
                assert first.locator('#deck-cards [data-card-key="horn"] .card-art').get_attribute('class').endswith('art-skone_horn')
                assert first.locator('#deck-cards [data-card-key="berserker"] .ability-seal svg').get_attribute('data-icon') == 'bear'
                assert first.locator('#deck-cards [data-card-key="skone_ghost"] .combat-seal').get_attribute('data-icon') == 'agile'
                assert first.locator('#deck-cards [data-card-key="skone_ghost"] .ability-seal').get_attribute('data-ability') == 'berserker'
                assert first.locator('#collection [data-card-key="skone_bear"], #deck-cards [data-card-key="skone_bear"]').count() == 0
                assert first.locator('#collection [data-card-key="skone_sailor"] .ability-seal svg').get_attribute('data-icon') == 'stormborn'
                assert first.locator('#collection [data-card-key="skone_skald"] .ability-seal').get_attribute('data-ability') == 'morale'
                assert first.locator('#deck-cards [data-card-key="ranger"] .ability-seal').get_attribute('data-ability') == 'stormborn'
                assert first.locator('#collection [data-card-key="skone_jarl"] .ability-seal').get_attribute('data-ability') == 'stormborn'
                for key, name in [('ranger','Воительница Яра'), ('young_berserker','Воительница Сконе'), ('berserker','Хельм Безумный')]:
                    assert first.locator(f'#deck-cards [data-card-key="{key}"]').get_attribute('aria-label').startswith(name)
                for width, height in [(1920,1080),(1366,768),(1280,720)]:
                    first.set_viewport_size({'width':width, 'height':height})
                    assert_lobby_fits(first)
                    first.screenshot(path=str(output / f'skone-lobby-{width}x{height}.png'))
                first.set_viewport_size({'width':1440, 'height':1000})
                first.locator('#leader-select').select_option('skone_horn')
                second.goto(f'{url}/?room={code}')
                second.locator('#player-name').fill('Ярл')
                second.locator('#join-room').click()
                second.wait_for_selector('#connection.online')
                second.locator('#faction-select').select_option('skone')
                first.locator('#ready-button').click()
                second.locator('#ready-button').click()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='visible')
                    page.locator('#mulligan-button').click()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='hidden')
                    assert_game_fits(page)
                    assert page.locator('.deck-pile[data-faction="skone"] .valknut-mark').count() == 2
                    assert page.locator('.deck-pile').evaluate_all("els => els.every(el => getComputedStyle(el).backgroundImage.includes('172, 147, 192'))")

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
                        page.wait_for_selector('#connection.online')
                        page.locator('.combat-row').first.wait_for()

                game = fixture(['horn', 'skone_heir'], ['knight'], 'skone_horn')
                put(game, 0, 'skone_heir', Row.RANGED)
                load(game)
                first.locator('#leader-button').click()
                first.locator('#leader-dialog').wait_for(state='visible')
                assert first.locator('#leader-apply').is_disabled()
                first.locator('#leader-rows [data-row="ranged"]').click()
                assert first.locator('#leader-apply').is_enabled()
                first.wait_for_function("() => document.querySelector('#leader-preview').getAnimations().every(a => a.playState !== 'running')")
                first.screenshot(path=str(output / 'skone-battlecry-selection.png'))
                first.locator('#leader-cancel').click()
                assert snapshot(first, code)['game']['version'] == 0
                first.locator('#leader-button').click()
                first.locator('#leader-rows [data-row="ranged"]').click()
                first.locator('#leader-apply').click()
                wait_version(first, 0)
                for page in pages:
                    page.locator('.leader-standard .art-skone_horn').wait_for()
                assert snapshot(first, code)['game']['players'][0]['rows']['ranged'] == 8
                first.screenshot(path=str(output / 'skone-battlecry-field.png'))

                game = fixture(['skone_heir'], ['skone_heir'], 'skone_storm', 'skone_rage')
                game.round_number = 2
                game.players[0].lives, game.players[1].lives = 1, 2
                put(game, 0, 'skone_heir')
                for player in game.players:
                    player.discard = [game._new_card(k) for k in ('skone_medic','ranger','skone_bard')]
                    player.passed = True
                game.rng = random.Random(2)
                game._end_round()
                load(game)
                for side in (0, 1):
                    chooser = pages[side]
                    chooser.locator('#choice-dialog').wait_for(state='visible')
                    assert pages[1-side].locator('#choice-dialog').is_hidden()
                    if side == 0:
                        chooser.screenshot(path=str(output / 'skone-third-round-medic.png'))
                    version = snapshot(chooser, code)['game']['version']
                    chooser.locator('#choice-cards [data-choice-id]').first.click()
                    wait_version(chooser, version)
                for page in pages:
                    page.locator('#choice-dialog').wait_for(state='hidden')
                    assert snapshot(page, code)['game']['turn'] == 0
                    assert [len(player['board']) for player in snapshot(page, code)['game']['players']] == [3, 3]
                for width, height in [(1440,1000),(1366,768),(390,844),(844,390)]:
                    first.set_viewport_size({'width':width, 'height':height})
                    assert_game_fits(first)
                first.set_viewport_size({'width':1440, 'height':1000})
                first.screenshot(path=str(output / 'skone-third-round.png'))

                game = fixture(['storm','horn','clear','skone_heir'], ['skone_heir'], 'skone_rage', 'skone_storm')
                game.players[1].passed = True
                ivar = put(game, 0, 'skone_ghost', Row.RANGED)
                enemy = put(game, 1, 'skone_ghost', Row.MELEE)
                rolf = put(game, 0, 'skone_sailor')
                load(game)
                first.locator('#leader-button').click()
                first.locator('#leader-apply').click()
                wait_version(first, 0)
                for page in pages:
                    page.locator(f'[data-card-id="{ivar.id}"][data-card-key="skone_bear"]').wait_for()
                    assert page.locator(f'[data-card-id="{enemy.id}"]').get_attribute('data-card-key') == 'skone_ghost'
                for key, expected in [('storm', 8), ('horn', 16), ('clear', 8)]:
                    current = snapshot(first, code)['game']
                    card = next(c for c in current['players'][0]['hand'] if c['key'] == key)
                    move = next(m for m in current['moves'] if m.get('card_id') == card['id'] and (key != 'horn' or m.get('row') == 'siege'))
                    click_move(first, move)
                    wait_version(first, current['version'])
                    for page in pages:
                        page.wait_for_function('''({id,power}) => document.querySelector(`[data-card-id="${id}"] .card-power`)?.textContent === String(power)''',
                                               arg={'id':rolf.id,'power':expected})
                    if key == 'horn':
                        first.screenshot(path=str(output / 'skone-stormborn-stacking.png'))
                assert not errors, errors
                print(json.dumps({'browser':channel,'skone_deck':'ok','valknut':'ok','battlecry_rows':'ok',
                                  'third_round_medics_both_sides':'ok','responsive':'ok','own_berserkers_only':'ok',
                                  'stormborn_stacking':'ok','agile_ivar':'ok','js_errors':errors}))
            except Exception:
                for side, page in enumerate(pages):
                    with suppress(Exception):
                        page.screenshot(path=str(output / f'skone-failure-{side}.png'), full_page=True)
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
