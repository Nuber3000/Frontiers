"""Local decks/history survive reloads, rematches and room changes without layout shifts."""

import argparse
import asyncio
from contextlib import suppress
import json
from pathlib import Path
import socket
import threading
import time

from playwright.sync_api import sync_playwright
import uvicorn

from frontiers.app import create_app
from browser_smoke import assert_lobby_fits, snapshot, wait_version


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
            browser = p.chromium.launch(headless=True, channel=channel)
            contexts = [browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce') for _ in range(2)]
            pages = [ctx.new_page() for ctx in contexts]
            for page in pages:
                page.set_default_timeout(15000)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('dialog', lambda dialog: dialog.accept())
            first, second = pages
            try:
                first.goto(url)
                first.locator('#player-name').fill('Хранитель')
                first.locator('#create-room').click()
                first.wait_for_selector('#connection.online')
                code = first.locator('#room-label').inner_text()
                original = first.locator('#deck-count').inner_text()

                def save(name):
                    first.locator('#saved-decks').click()
                    first.locator('#saved-deck-name').fill(name)
                    first.locator('.save-deck-form button').click()
                    first.locator('.saved-deck-item').filter(has=first.get_by_role('heading', name=name, exact=True)).wait_for()
                    first.locator('#close-info').click()

                save('Стража <img src=x>')
                first.locator('#collection .card-adjust button').first.click()
                first.locator('#leader-select').select_option('fog')
                modified = first.locator('#deck-count').inner_text()
                save('Другая тактика')
                first.reload()
                first.wait_for_selector('#connection.online')
                assert first.locator('#deck-count').inner_text() == modified
                assert first.locator('#leader-select').input_value() == 'fog'
                first.locator('#deck-preset').select_option(label='Стража <img src=x>')
                assert first.locator('#deck-count').inner_text() == original
                assert first.locator('#leader-select').input_value() == 'sun'
                first.locator('#faction-select').select_option('skone')
                save('Север')
                first.locator('#saved-decks').click()
                first.locator('.saved-deck-item').filter(has=first.get_by_role('heading', name='Другая тактика', exact=True)).locator('[data-action="load"]').click()
                assert first.locator('#faction-select').input_value() == 'burgundy'
                assert first.locator('#deck-count').inner_text() == modified
                first.locator('#collection .card-adjust button').first.click()
                updated = first.locator('#deck-count').inner_text()
                first.locator('#saved-decks').click()
                row = first.locator('.saved-deck-item').filter(has=first.get_by_role('heading', name='Другая тактика', exact=True))
                row.locator('[data-action="update"]').click()
                first.locator('.saved-deck-item').filter(has=first.get_by_role('heading', name='Север', exact=True)).locator('[data-action="delete"]').click()
                assert first.locator('.saved-deck-item').count() == 2
                assert first.locator('.saved-decks img').count() == 0
                first.screenshot(path=str(output / 'saved-decks.png'))
                first.locator('#close-info').click()
                first.reload()
                first.wait_for_selector('#connection.online')
                first.locator('#deck-preset').select_option(label='Другая тактика')
                assert first.locator('#deck-count').inner_text() == updated

                second.goto(f'{url}/?room={code}')
                second.locator('#player-name').fill('Соперник')
                second.locator('#join-room').click()
                second.wait_for_selector('#connection.online')
                assert second.locator('#deck-preset option[value^="saved:"]').count() == 0
                for page in pages:
                    page.locator('#ready-button').click()
                    if page is first:
                        assert first.locator('#deck-preset').is_disabled()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='visible')
                    page.locator('#mulligan-button').click()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='hidden')

                def finish_and_inspect(expected_count, concede=False):
                    if concede:
                        first.locator('#concede-button').click()
                    else:
                        while snapshot(first, code)['game']['phase'] != 'finished':
                            game = snapshot(first, code)['game']
                            pages[game['turn']].locator('#pass-button').click()
                            for page in pages:
                                wait_version(page, game['version'])
                    for page in pages:
                        page.locator('#result-dialog').wait_for(state='visible')
                        page.locator('#result-continue').click()
                        assert page.locator('#match-result').count() == 0
                        page.locator('#match-history').click()
                        assert page.locator('.history-item').count() == expected_count
                        page.locator('#close-info').click()
                    for width, height in [(1920, 1080), (1366, 768), (1280, 720), (1024, 768)]:
                        first.set_viewport_size({'width': width, 'height': height})
                        assert_lobby_fits(first)
                    first.screenshot(path=str(output / 'rematch-lobby.png'))
                    first.set_viewport_size({'width': 1440, 'height': 1000})

                finish_and_inspect(1)
                first.reload()
                first.locator('#result-dialog').wait_for(state='visible')
                first.locator('#result-continue').click()
                first.locator('#match-history').click()
                assert first.locator('.history-item').count() == 1
                assert first.locator('.history-scores span').count() == 2
                first.screenshot(path=str(output / 'match-history.png'))
                first.locator('#close-info').click()
                for page in pages:
                    page.locator('#ready-button').click()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='visible')
                    page.locator('#mulligan-button').click()
                for page in pages:
                    page.locator('#mulligan-dialog').wait_for(state='hidden')
                finish_and_inspect(2, concede=True)
                first.locator('#leave-view').click()
                first.locator('#landing-history').click()
                assert first.locator('.history-item').count() == 2
                first.locator('#close-info').click()
                first.locator('#create-room').click()
                first.wait_for_selector('#connection.online')
                assert first.locator('#deck-count').inner_text() == updated
                assert first.locator('#leader-select').input_value() == 'fog'

                # Corrupt/outdated data and denied/quota-limited storage must not stop play.
                resilience = first.evaluate('''async () => {
                  const catalog = await (await fetch('/api/catalog')).json();
                  const prefix = 'frontiers.profile.v1.';
                  const decks = localStorage.getItem(prefix + 'decks');
                  localStorage.setItem(prefix + 'decks', '{broken');
                  const profile = new FrontiersProfile(catalog);
                  const invalid = profile.decks().length === 0;
                  localStorage.setItem(prefix + 'decks', JSON.stringify([{id:'bad', name:'bad', faction:'burgundy', leader:'sun', cards:['unknown-card']}]));
                  const obsolete = profile.decks().length === 0;
                  localStorage.setItem(prefix + 'decks', decks);
                  const original = Storage.prototype.setItem;
                  let handled = false;
                  Storage.prototype.setItem = function() { throw new DOMException('full', 'QuotaExceededError'); };
                  try { profile.saveDeck('test', {faction:'burgundy',leader:'sun',cards:[]}); }
                  catch (error) { handled = error.message.includes('сохранить'); }
                  finally { Storage.prototype.setItem = original; }
                  return {invalid, obsolete, handled};
                }''')
                assert all(resilience.values()), resilience
                for width, height in [(390, 844), (844, 390)]:
                    first.set_viewport_size({'width': width, 'height': height})
                    first.locator('#saved-decks').click()
                    assert first.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    first.locator('#close-info').click()
                assert not errors, errors
                print(json.dumps({'saved_decks': 'ok', 'draft_reload': 'ok', 'rematch_history': 'ok',
                    'history_dedup': 'ok', 'responsive_lobby': 'ok', 'storage_errors': resilience, 'js_errors': errors}))
            except Exception:
                for side, page in enumerate(pages):
                    with suppress(Exception):
                        page.screenshot(path=str(output / f'profile-failure-{side}.png'), full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        loop.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', default='msedge')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts' / 'browser')
    options = parser.parse_args()
    run(options.browser, options.output)
