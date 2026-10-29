"""Казнь в двух браузерах с контролируемым состоянием настоящего игрового сервера.

Запуск: python tests/browser_scorch.py --browser msedge
Фикстуры меняются только внутри этого теста; отладочных HTTP-методов в игре нет.
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
from browser_smoke import click_move, snapshot, wait_version
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel=None if channel == 'chromium' else channel)
            contexts = [browser.new_context(viewport={'width': width, 'height': height})
                        for width, height in [(1440, 1000), (1366, 768)]]
            pages = [context.new_page() for context in contexts]
            for page in pages:
                page.set_default_timeout(12000)
                page.on('pageerror', lambda error: errors.append(str(error)))
            first, second = pages
            try:
                first.goto(url)
                first.locator('#player-name').fill('Первый')
                first.locator('#create-room').click()
                first.wait_for_selector('#connection.online')
                code = first.locator('#room-label').inner_text()
                second.goto(f'{url}/?room={code}')
                second.locator('#player-name').fill('Второй')
                second.locator('#join-room').click()
                second.wait_for_selector('#connection.online')

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
                        page.locator('.combat-row').first.wait_for(state='visible')
                        page.evaluate('''async () => {
                          await Promise.all([...document.querySelectorAll('.row-cards .card-art')].map(async art => {
                            const image = new Image(); image.src = getComputedStyle(art).backgroundImage.slice(5, -2);
                            await image.decode();
                          }));
                          window.burnObservations = [];
                          const observed = new WeakSet();
                          new MutationObserver(() => {
                            for (const burn of document.querySelectorAll('.scorch-burn')) {
                              if (observed.has(burn)) continue;
                              observed.add(burn);
                              window.burnObservations.push({id: burn.dataset.burnId,
                                reduced: burn.classList.contains('reduced-motion')});
                            }
                          }).observe(document.querySelector('#arena'), {subtree: true, childList: true});
                        }''')

                def verify(move, victims, *, screenshot=None, terminal=False, reduced=False):
                    before = snapshot(first, code)['game']['version']
                    click_move(first, move)
                    for page in pages:
                        wait_version(page, before)
                    expected = {card.id for card in victims}
                    for page in pages:
                        assert set(snapshot(page, code)['game']['scorched']) == expected
                        if not reduced:
                            assert set(page.locator('.scorch-burn').evaluate_all('items => items.map(item => item.dataset.burnId)')) == expected
                            page.locator('#scorch-effects').wait_for(state='visible')
                            page.wait_for_function('''() => {
                              const canvas = document.querySelector('#scorch-effects'), burn = document.querySelector('.scorch-burn');
                              if (!canvas || !burn) return false;
                              const rect = burn.getBoundingClientRect(), ratio = canvas.width / innerWidth;
                              const x = Math.max(0, Math.floor(rect.left * ratio)), y = Math.max(0, Math.floor(rect.top * ratio));
                              const width = Math.min(canvas.width - x, Math.ceil(rect.width * ratio));
                              const height = Math.min(canvas.height - y, Math.ceil(rect.height * ratio));
                              const data = canvas.getContext('2d').getImageData(x, y, width, height).data;
                              return data.some((value, index) => index % 4 === 3 && value > 0);
                            }''')
                        for card_id in expected:
                            assert page.locator(f'.row-cards [data-card-id="{card_id}"]').count() == 0
                        if terminal:
                            assert page.locator('#result-dialog').is_hidden()
                    if screenshot:
                        for side, page in enumerate(pages):
                            page.wait_for_function('''() => {
                              const burn = document.querySelector('.scorch-burn > .card');
                              const animation = burn?.getAnimations()[0];
                              return animation && animation.currentTime > 900 && animation.currentTime < 2100;
                            }''')
                            name = screenshot if side == 0 else screenshot.replace('.png', '-opponent.png')
                            page.screenshot(path=str(output / name))
                    for page in pages:
                        page.wait_for_selector('.scorch-burn', state='detached', timeout=5000)
                        observations = page.evaluate('window.burnObservations')
                        assert {item['id'] for item in observations} == expected, observations
                        if reduced:
                            assert all(item['reduced'] for item in observations), observations
                            assert page.locator('#scorch-effects').is_hidden()
                        if terminal:
                            page.locator('#result-dialog').wait_for(state='visible', timeout=30000)

                # Ничья по силе уничтожает отряды с обеих сторон, герои сохраняются.
                game = fixture(['scorch', 'knight'], ['knight'])
                victims = [put(game, 0, 'knight'), put(game, 1, 'knight'), put(game, 1, 'knight')]
                hero = put(game, 0, 'regent')
                load(game)
                verify({'type': 'play', 'card_id': game.players[0].hand[0].id}, victims, screenshot='scorch-burning.png')
                assert first.locator(f'.row-cards [data-card-id="{hero.id}"]').count() == 1
                revision = snapshot(first, code)['revision']

                async def repeat_snapshot():
                    room = app.state.rooms.rooms[code]
                    async with room.lock:
                        room.changed()
                        await room.broadcast()
                asyncio.run_coroutine_threadsafe(repeat_snapshot(), loop).result(timeout=5)
                for page in pages:
                    page.wait_for_function('revision => Number(document.body.dataset.revision) > revision', arg=revision)
                    assert page.locator('.scorch-burn').count() == 0, 'A presence update repeated the execution'
                first.reload()
                first.wait_for_selector('#connection.online')
                assert first.locator('.scorch-burn').count() == 0, 'Reload repeated an old execution'

                # Казнь в способности лидера затрагивает только выбранную линию врага.
                for leader, row, key in [('mortar', 'ranged', 'crossbow'), ('war', 'siege', 'ballista')]:
                    game = fixture(['knight'], ['knight'], leader0=leader)
                    victims = [put(game, 1, key), put(game, 1, key)]
                    untouched = put(game, 1, 'knight')
                    load(game)
                    verify({'type': 'leader'}, victims)
                    assert first.locator(f'.row-cards [data-card-id="{untouched.id}"]').count() == 1

                game = fixture(['fire_walker', 'knight'], ['knight'])
                victims = [put(game, 1, 'knight'), put(game, 1, 'knight')]
                load(game)
                verify({'type': 'play', 'card_id': game.players[0].hand[0].id, 'row': 'melee'}, victims)

                # Следующий ход и повторная перерисовка не перезапускают уже начатое сгорание.
                game = fixture(['scorch', 'knight'], ['scorch', 'knight'])
                own = put(game, 0, 'knight')
                enemies = [put(game, 1, 'crossbow') for _ in range(2)]
                load(game)
                click_move(first, {'type': 'play', 'card_id': game.players[0].hand[0].id})
                for page in pages:
                    wait_version(page, 0)
                second.locator(f'#hand [data-card-id="{game.players[1].hand[1].id}"]').click()
                assert len(second.evaluate('window.burnObservations')) == 2
                click_move(second, {'type': 'play', 'card_id': game.players[1].hand[0].id})
                for page in pages:
                    wait_version(page, 1)
                for page in pages:
                    assert set(page.evaluate('window.burnObservations.map(item => item.id)')) == {own.id, *(card.id for card in enemies)}
                    assert page.locator(f'.scorch-burn[data-burn-id="{own.id}"]').count() == 1
                for page in pages:
                    page.wait_for_selector('.scorch-burn', state='detached', timeout=5000)
                    assert len(page.evaluate('window.burnObservations')) == 3

                # Чучело и обычная очистка поля не должны запускать огонь.
                game = fixture(['decoy', 'knight'], ['knight'])
                target = put(game, 0, 'knight')
                load(game)
                version = game.version
                click_move(first, {'type': 'play', 'card_id': game.players[0].hand[0].id, 'target_id': target.id})
                for page in pages:
                    wait_version(page, version)
                for _ in range(2):
                    current = snapshot(first, code)['game']
                    pages[current['turn']].locator('#pass-button').click()
                    for page in pages:
                        wait_version(page, current['version'])
                for page in pages:
                    assert page.evaluate('window.burnObservations') == []

                # Если Казнь завершает матч, итоговый экран ждёт завершения сгорания.
                game = fixture(['scorch'], ['knight'])
                game.players[0].leader_used = True
                game.players[1].passed = True
                game.players[1].lives = 1
                put(game, 0, 'regent')
                victims = [put(game, 1, 'knight')]
                load(game)
                verify({'type': 'play', 'card_id': game.players[0].hand[0].id}, victims, terminal=True)

                # Фоновая вкладка получает тот же ход, но показывает огонь при возвращении.
                game = fixture(['scorch', 'knight'], ['knight'])
                victim = put(game, 1, 'knight')
                load(game)
                second.set_viewport_size({'width': 390, 'height': 844})
                second.evaluate('''() => {
                  Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});
                  document.dispatchEvent(new Event('visibilitychange'));
                }''')
                click_move(first, {'type': 'play', 'card_id': game.players[0].hand[0].id})
                wait_version(first, 0)
                second.wait_for_selector('#opponent-play', state='attached')
                first.wait_for_selector('.scorch-burn', state='detached', timeout=5000)
                assert second.locator('body').get_attribute('data-game-version') == '0'
                assert second.locator('#opponent-play').get_attribute('data-stage') == 'reveal'
                assert second.locator('#scorch-effects').is_hidden()
                second.evaluate('''() => {
                  delete document.visibilityState;
                  document.dispatchEvent(new Event('visibilitychange'));
                }''')
                wait_version(second, 0)
                second.wait_for_selector('#opponent-play', state='detached')
                assert second.locator(f'.scorch-burn[data-burn-id="{victim.id}"]').count() == 1
                second.locator('#scorch-effects').wait_for(state='visible')
                second.wait_for_function("() => document.querySelector('.scorch-burn > .card').getAnimations()[0].currentTime > 800")
                second.screenshot(path=str(output / 'scorch-returned-tab.png'))
                second.wait_for_selector('.scorch-burn', state='detached', timeout=5000)
                assert len(second.evaluate('window.burnObservations')) == 1

                for page in pages:
                    page.emulate_media(reduced_motion='reduce')
                game = fixture(['scorch', 'knight'], ['knight'])
                victims = [put(game, 1, 'knight')]
                load(game)
                verify({'type': 'play', 'card_id': game.players[0].hand[0].id}, victims, reduced=True)
                assert not errors, errors
                print(json.dumps({'browser': channel, 'scorch': 'ok', 'tied_victims': 'ok',
                                  'leader_scorch': 'ok', 'unit_scorch': 'ok', 'no_false_burns': 'ok',
                                  'reconnect': 'ok', 'consecutive_actions': 'ok', 'final_round': 'ok', 'reduced_motion': 'ok',
                                  'both_canvases': 'ok', 'background_tab': 'ok',
                                  'js_errors': errors}))
            except Exception:
                for index, page in enumerate(pages):
                    with suppress(Exception):
                        page.screenshot(path=str(output / f'scorch-failure-{index}.png'))
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
    parser.add_argument('--browser', choices=['msedge', 'chrome', 'chromium'], default='msedge' if os.name == 'nt' else 'chromium')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts' / 'browser')
    options = parser.parse_args()
    run(options.browser, options.output)
