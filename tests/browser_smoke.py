"""Проверка интерфейса в двух независимых браузерных сессиях.

Запуск: python tests/browser_smoke.py --browser msedge
Для Chromium: python -m playwright install chromium
"""

import argparse
from contextlib import suppress
import html
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def snapshot(page, code):
    return page.evaluate("""async code => {
      const response = await fetch(`/api/rooms/${code}`);
      if (!response.ok) throw new Error('Cannot read room');
      return await response.json();
    }""", code)


def wait_version(page, version):
    page.wait_for_function("version => Number(document.body.dataset.gameVersion) > version", arg=version)


def assert_game_fits(page):
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    metrics = page.evaluate("""() => {
      const selectors = ['#arena', '.battlefield', '.hand-panel', '#hand',
        '#leader-button', '#pass-button', '#concede-button', '#fullscreen-button', '.combat-row'];
      const failures = [];
      for (const selector of selectors) {
        for (const element of document.querySelectorAll(selector)) {
          const rect = element.getBoundingClientRect();
          if (rect.height <= 0 || rect.top < -1 || rect.bottom > innerHeight + 1)
            failures.push({selector, top: rect.top, bottom: rect.bottom, height: rect.height});
        }
      }
      for (const card of document.querySelectorAll('#hand .card, .row-cards .card, .row-special .card')) {
        const rect = card.getBoundingClientRect();
        const bounds = card.parentElement.getBoundingClientRect();
        if (rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1)
          failures.push({selector: 'card clipped vertically', top: rect.top, bottom: rect.bottom,
            parentTop: bounds.top, parentBottom: bounds.bottom});
        if (card.parentElement.classList.contains('row-cards')) {
          const art = card.querySelector('.card-art').getBoundingClientRect();
          if (card.querySelector('.card-name').getBoundingClientRect().height > 0)
            failures.push({selector: 'visible name on battlefield card'});
          if (art.height < rect.height - 4)
            failures.push({selector: 'illustration does not fill battlefield card', art: art.height, card: rect.height});
          if (innerHeight >= 600 && rect.height < bounds.height * .85)
            failures.push({selector: 'battlefield card too small', card: rect.height, row: bounds.height});
        }
        if (card.parentElement.id === 'hand') {
          if (card.querySelector('.card-name').getBoundingClientRect().height > 0)
            failures.push({selector: 'visible name on hand card'});
          if (card.querySelector('.card-art').getBoundingClientRect().height < rect.height - 4)
            failures.push({selector: 'illustration does not fill hand card'});
          for (const seal of card.querySelectorAll('.ability-seal, .combat-seal')) {
            if (innerHeight >= 600 && seal.getBoundingClientRect().width < 22)
              failures.push({selector: 'hand ability icon too small'});
          }
        }
      }
      if (document.querySelector('#copy-invite').getBoundingClientRect().height > 0)
        failures.push({selector: 'invitation button visible during match'});
      if (!document.querySelector('.round-panel #turn-banner'))
        failures.push({selector: 'turn status outside round panel'});
      const pass = document.querySelector('#pass-button');
      const concede = document.querySelector('#concede-button');
      if (pass.parentElement !== concede.parentElement ||
          Math.abs(pass.getBoundingClientRect().top - concede.getBoundingClientRect().top) > 1)
        failures.push({selector: 'concede button is not next to pass'});
      const battlefield = document.querySelector('.battlefield').getBoundingClientRect();
      if (document.querySelector('.combat-row').getBoundingClientRect().top - battlefield.top > 1)
        failures.push({selector: 'unused space above combat rows'});
      if (battlefield.top > 1)
        failures.push({selector: 'top toolbar still takes space from battlefield', top: battlefield.top});
      const connection = document.querySelector('#room-status').getBoundingClientRect();
      if (innerWidth - connection.right > 24)
        failures.push({selector: 'connection status is not at right edge'});
      const boardCard = document.querySelector('.row-cards .card.unit');
      const handCard = document.querySelector('#hand .card.unit');
      if (boardCard && handCard) {
        const contentWidth = card => {
          const style = getComputedStyle(card);
          return card.getBoundingClientRect().width - parseFloat(style.borderLeftWidth) - parseFloat(style.borderRightWidth);
        };
        for (const selector of ['.card-power', '.combat-seal', '.ability-seal']) {
          const onBoard = boardCard.querySelector(selector);
          const inHand = handCard.querySelector(selector);
          if (!onBoard || !inHand) continue;
          const boardStyle = getComputedStyle(onBoard), handStyle = getComputedStyle(inHand);
          const boardFraction = onBoard.getBoundingClientRect().width / contentWidth(boardCard);
          const handFraction = inHand.getBoundingClientRect().width / contentWidth(handCard);
          if (Math.abs(boardFraction - handFraction) > .02 ||
              (selector === '.card-power' && Math.abs(parseFloat(boardStyle.fontSize) / contentWidth(boardCard) -
                parseFloat(handStyle.fontSize) / contentWidth(handCard)) > .02))
            failures.push({selector: 'different badge proportions in hand and on board', badge: selector,
              boardFraction, handFraction});
        }
      }
      for (const portrait of document.querySelectorAll('.leader-art')) {
        const rect = portrait.getBoundingClientRect();
        if (!rect.width || !rect.height) continue;
        const matrix = portrait.getScreenCTM();
        if (Math.abs(matrix.a / matrix.d - 1) > .001)
          failures.push({selector: 'distorted leader portrait', scaleX: matrix.a, scaleY: matrix.d});
        const frame = portrait.parentElement.getBoundingClientRect();
        if (Math.abs(frame.width / frame.height - .75) > .03)
          failures.push({selector: 'leader card aspect ratio', width: frame.width, height: frame.height});
      }
      return {height: innerHeight, width: innerWidth,
        scrollHeight: document.documentElement.scrollHeight,
        scrollWidth: document.documentElement.scrollWidth, failures};
    }""")
    assert metrics["scrollHeight"] <= metrics["height"] + 1, metrics
    assert metrics["scrollWidth"] <= metrics["width"] + 1, metrics
    assert not metrics["failures"], metrics


def click_move(page, move):
    kind = move["type"]
    if kind == "play":
        page.locator(f'#hand [data-card-id="{move["card_id"]}"]').click()
        if "target_id" in move:
            page.locator(f'#own-rows [data-card-id="{move["target_id"]}"]').click()
        elif "row" in move:
            page.locator(f'.combat-row.droppable[data-row="{move["row"]}"]').click(position={"x": 10, "y": 15})
        else:
            page.locator("#selection-info .primary").click()
    elif kind == "choose":
        page.locator(f'#choice-cards [data-choice-id="{move["card_id"]}"][data-choice-row="{move["row"]}"]').click()
    elif kind == "leader":
        page.locator("#leader-button").click()
    elif kind == "pass":
        page.locator("#pass-button").click()
    else:
        raise AssertionError(f"Unexpected browser move: {move}")


def check_fullscreen(page, code, output):
    version = snapshot(page, code)['game']['version']
    toggle = page.locator('#fullscreen-button')
    toggle.click()
    page.wait_for_function('() => document.fullscreenElement === document.documentElement')
    page.wait_for_function('() => document.querySelector("#fullscreen-button").getAttribute("aria-pressed") === "true"')
    assert_game_fits(page)
    page.screenshot(path=str(output / 'fullscreen.png'))
    toggle.click()
    page.wait_for_function('() => document.fullscreenElement === null')
    page.wait_for_function('() => document.querySelector("#fullscreen-button").getAttribute("aria-pressed") === "false"')
    toggle.click()
    page.wait_for_function('() => document.fullscreenElement === document.documentElement')
    # Выход, инициированный браузером, должен обновлять кнопку так же, как Esc.
    page.evaluate('document.exitFullscreen()')
    page.wait_for_function('() => document.querySelector("#fullscreen-button").getAttribute("aria-pressed") === "false"')
    assert toggle.get_attribute('aria-label') == 'На весь экран'
    assert snapshot(page, code)['game']['version'] == version
    assert_game_fits(page)


def assert_lobby_fits(page):
    metrics = page.evaluate("""() => {
      const collection = document.querySelector('#collection').getBoundingClientRect();
      const leader = document.querySelector('.commander-panel').getBoundingClientRect();
      const deck = document.querySelector('#deck-cards').getBoundingClientRect();
      const ready = document.querySelector('#ready-button').getBoundingClientRect();
      return {height: innerHeight, width: innerWidth, scrollHeight: document.documentElement.scrollHeight,
        scrollWidth: document.documentElement.scrollWidth, readyBottom: ready.bottom,
        ordered: collection.right < leader.left && leader.right < deck.left};
    }""")
    assert metrics['scrollHeight'] <= metrics['height'] + 1, metrics
    assert metrics['scrollWidth'] <= metrics['width'] + 1, metrics
    assert metrics['readyBottom'] <= metrics['height'], metrics
    assert metrics['ordered'], metrics


def save_artwork_gallery(browser, url, catalog, output):
    tiles = []
    for card in catalog['cards']:
        tiles.append(f'<article><div class="gallery-art card-art art-{card["key"]}"></div>'
                     f'<p>{html.escape(card["name"])}</p></article>')
    for key, leader in catalog['leaders'].items():
        tiles.append(f'<article><img src="{url}/static/leader_{key}.png">'
                     f'<p>Франциск · {html.escape(leader["name"])}</p></article>')
    gallery = browser.new_page(viewport={'width': 1540, 'height': 1200})
    try:
        gallery.set_content(f'''<!doctype html><html lang="ru"><meta charset="utf-8">
          <link rel="stylesheet" href="{url}/static/cards.css">
          <link rel="stylesheet" href="{url}/static/artwork.css">
          <style>*{{box-sizing:border-box}}body{{margin:0;padding:20px;background:#15140f;color:#e8d8b6;font:14px Georgia}}
          header{{display:flex;align-items:center;gap:22px;margin-bottom:18px}}h1{{font-weight:400;margin:0}}
          main{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:14px}}
          article{{margin:0;min-width:0;background:#282316;border:1px solid #80683e}}
          .gallery-art,article img{{display:block;width:100%;aspect-ratio:3/4;object-fit:cover}}
          article p{{margin:0;min-height:42px;padding:7px;text-align:center}}</style>
          <header><h1>Frontiers · все иллюстрации, включая резерв Сконе</h1></header>
          <main>{''.join(tiles)}</main></html>''')
        signatures = gallery.evaluate('''async () => {
          await Promise.all([...document.querySelectorAll('link')].map(link => link.sheet ? null :
            new Promise(resolve => link.addEventListener('load', resolve, {once:true}))));
          const result = [];
          for (const art of document.querySelectorAll('.gallery-art')) {
            const style = getComputedStyle(art), source = style.backgroundImage;
            const image = new Image(); image.src = source.slice(5, -2); await image.decode();
            result.push(source + style.backgroundPosition);
          }
          for (const image of document.querySelectorAll('article img')) {
            await image.decode(); result.push(image.src);
          }
          return result;
        }''')
        assert len(signatures) == 49 and len(set(signatures)) == 49, signatures
        gallery.screenshot(path=str(output / 'card-gallery.png'), full_page=True)
    finally:
        gallery.close()


def save_portrait_review(browser, page, url, output):
    markup = page.evaluate('''() => ['fire_walker','regent','field_medic','champion','spy_hero','veteran','company_captain'].map(key => {
      const card = document.querySelector(`#collection [data-card-key="${key}"], #deck-cards [data-card-key="${key}"]`);
      return card.outerHTML;
    }).join('')''')
    review = browser.new_page(viewport={'width': 810, 'height': 860})
    try:
        review.set_content(f'''<!doctype html><html lang="ru"><meta charset="utf-8">
          <link rel="stylesheet" href="{url}/static/styles.css">
          <link rel="stylesheet" href="{url}/static/cards.css">
          <link rel="stylesheet" href="{url}/static/artwork.css">
          <style>body{{padding:24px}}h1{{font-size:26px;letter-spacing:0;margin:0 0 20px}}
          main{{display:grid;grid-template-columns:repeat(3,230px);gap:20px;padding:0;margin:0}}
          main .card{{width:230px;height:365px}}</style>
          <h1>Портреты: верх изображения полностью в рамке</h1><main>{markup}</main></html>''')
        review.evaluate('''async () => {
          for(const art of document.querySelectorAll('.card-art')) {
            const style = getComputedStyle(art);
            if(style.backgroundPositionY !== '0%') throw new Error('Incorrect portrait alignment');
            const image = new Image(); image.src = style.backgroundImage.slice(5,-2); await image.decode();
          }
        }''')
        review.screenshot(path=str(output / 'portraits-fixed.png'), full_page=True)
    finally:
        review.close()


def save_icon_review(browser, page, url, output):
    icons = page.evaluate('''() => [
      {name:'Габриэль фон Ард · ближний или дальний бой', selector:'[data-card-key="herald"] .combat-seal', card:'herald'},
      {name:'Наследие · призыв после ухода в сброс', selector:'[data-ability="avenger"] svg', card:'watchman'}
    ].map(item => ({name:item.name, icon:document.querySelector(item.selector).outerHTML,
      card:document.querySelector(`[data-card-key="${item.card}"]`).outerHTML}))''')
    blocks = []
    for index, item in enumerate(icons):
        samples = ''.join(f'<div class="sample"><div class="badge b{size} color{index}">{item["icon"]}</div>'
                          f'<small>{size} px</small></div>' for size in (24, 32, 48, 96))
        blocks.append(f'<section><h2>{html.escape(item["name"])}</h2><div class="sizes">{samples}</div>'
                      f'<div class="card-preview">{item["card"]}</div></section>')
    review = browser.new_page(viewport={'width': 1024, 'height': 640})
    try:
        review.set_content(f'''<!doctype html><html lang="ru"><meta charset="utf-8">
          <link rel="stylesheet" href="{url}/static/styles.css">
          <link rel="stylesheet" href="{url}/static/cards.css">
          <link rel="stylesheet" href="{url}/static/artwork.css">
          <style>body{{padding:28px}}h1{{font-size:26px;letter-spacing:0;margin:0 0 22px}}
          main{{display:grid;grid-template-columns:1fr 1fr;gap:30px;padding:0;margin:0}}
          section{{padding:20px;border:1px solid #685331;background:#241f17}}h2{{font-size:20px;min-height:48px}}
          .sizes{{display:flex;gap:25px;align-items:end;justify-content:center;height:130px}}
          .sample{{text-align:center}}.sample small{{display:block;margin-top:10px;color:#a99a80;font-size:11px}}
          .badge{{display:grid;place-items:center;border-radius:50%;border:1px solid #735b31;color:#272a22}}
          .badge svg{{width:76%;height:76%;padding:0;border:0;background:transparent;box-shadow:none}}
          .color0{{background:#c59a45}}.color1{{background:#e2d9bd}}
          .b24{{width:24px;height:24px}}.b32{{width:32px;height:32px}}.b48{{width:48px;height:48px}}.b96{{width:96px;height:96px}}
          .card-preview{{display:flex;justify-content:center;margin-top:24px}}
          .card-preview .card{{width:145px;height:230px}}</style>
          <h1>Новые значки в размере карты и крупно</h1><main>{''.join(blocks)}</main></html>''')
        review.evaluate('''async () => {
          for(const art of document.querySelectorAll('.card-art')) {
            const image = new Image(); image.src = getComputedStyle(art).backgroundImage.slice(5,-2); await image.decode();
          }
        }''')
        review.screenshot(path=str(output / 'icons-updated.png'), full_page=True)
    finally:
        review.close()


def run(browser_channel, output):
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    errors = []
    with (output / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-m", "frontiers", "--port", str(port)],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urllib.request.urlopen(f"{url}/healthz", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.monotonic() > deadline or process.poll() is not None:
                        raise RuntimeError("Local server did not start; inspect server.log")
                    time.sleep(0.1)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, channel=None if browser_channel == "chromium" else browser_channel)
                contexts = [browser.new_context(viewport={"width": 1440, "height": 1100}) for _ in range(2)]
                pages = [context.new_page() for context in contexts]
                for page in pages:
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.set_default_timeout(12000)
                first, second = pages
                try:
                    first.goto(url)
                    first.locator("#player-name").fill("Алиса")
                    first.locator("#create-room").click()
                    first.locator("#room-label").wait_for(state="visible")
                    code = first.locator("#room-label").inner_text()
                    first.wait_for_selector("#connection.online")
                    for width, height in [(1920, 1080), (1366, 768), (1280, 720), (1024, 768)]:
                        first.set_viewport_size({"width": width, "height": height})
                        assert_lobby_fits(first)
                        first.screenshot(path=str(output / f"lobby-{width}x{height}.png"))
                    first.set_viewport_size({"width": 1440, "height": 1100})
                    first.screenshot(path=str(output / "lobby.png"), full_page=True)
                    catalog = first.evaluate("async () => (await fetch('/api/catalog')).json()")
                    save_artwork_gallery(browser, url, catalog, output)
                    save_portrait_review(browser, first, url, output)
                    save_icon_review(browser, first, url, output)
                    for key in catalog['leaders']:
                        first.locator('#leader-select').select_option(key)
                        assert first.locator('.leader-portrait .leader-art image').get_attribute('href').endswith(f'leader_{key}.png')
                    first.locator('#leader-select').select_option('sun')
                    ability_icons = first.evaluate("""async () => {
                      const catalog = await (await fetch('/api/catalog')).json();
                      const abilities = new Set(catalog.cards.filter(card => card.available).flatMap(card => card.abilities));
                      return [...abilities].map(ability => {
                        const seal = document.querySelector(`.ability-seal[data-ability="${ability}"]`);
                        const svg = seal?.querySelector('svg');
                        return {ability, icon: svg?.dataset.icon, geometry: svg?.innerHTML};
                      });
                    }""")
                    assert all(item['geometry'] and item['icon'] != 'unknown' for item in ability_icons), ability_icons
                    assert len({item['geometry'] for item in ability_icons}) == len(ability_icons), ability_icons
                    by_ability = {item['ability']: item['icon'] for item in ability_icons}
                    assert by_ability['morale'] == 'morale', by_ability
                    assert all(by_ability[key] == key for key in ('scorch_melee', 'scorch_ranged', 'scorch_siege')), by_ability
                    assert first.locator('#deck-preset option[value="forest"]').count() == 0
                    for key in ('berserker', 'young_berserker', 'mushroom', 'ranger', 'druid', 'storm'):
                        assert first.locator(f'#collection [data-card-key="{key}"], #deck-cards [data-card-key="{key}"]').count() == 0
                    gabriel = first.locator('[data-card-key="herald"]').first
                    assert 'Габриэль фон Ард' in gabriel.get_attribute('aria-label')
                    assert gabriel.locator('.combat-seal[data-icon="agile"]').count() == 1
                    first.get_by_role('button', name='Добавить: Ливень', exact=True).click()
                    assert first.locator('#deck-cards [data-card-key="rain"]').count() == 1
                    first.get_by_role('button', name='Убрать: Ливень', exact=True).click()
                    assert first.locator('#deck-cards [data-card-key="rain"]').count() == 0
                    first.locator('#collection-tabs').get_by_role('button', name='Дальний бой', exact=True).click()
                    assert first.locator('#collection .card').count() > 0
                    first.locator('#collection-tabs').get_by_role('button', name='Все карты', exact=True).click()
                    artwork = first.evaluate(r"""async () => {
                      const checks = [];
                      for (const key of ['decoy', 'rain', 'scorch', 'horn']) {
                        const art = document.querySelector(`#collection [data-card-key="${key}"] .card-art`);
                        const url = getComputedStyle(art).backgroundImage.match(/url\(["']?(.*?)["']?\)/)[1];
                        const image = new Image(); image.src = url; await image.decode();
                        checks.push({key, url, width: image.naturalWidth, height: image.naturalHeight});
                      }
                      return checks;
                    }""")
                    assert len({item['url'] for item in artwork}) == 4, artwork
                    assert all(item['width'] > 0 and item['height'] > 0 for item in artwork), artwork
                    first.locator('#collection-filter').select_option('special')
                    first.screenshot(path=str(output / 'special-cards.png'), full_page=True)
                    first.locator('#collection-filter').select_option('all')
                    second.goto(f"{url}/?room={code}")
                    second.locator("#player-name").fill("Борис")
                    second.locator("#join-room").click()
                    second.wait_for_selector("#connection.online")
                    second.locator("#deck-preset").select_option("guard")
                    first.locator("#leader-select").select_option("academy")
                    second.locator("#leader-select").select_option("fog")
                    first.locator("#collection .card").first.click()
                    first.locator("#close-info").click()
                    first.locator("#ready-button").click()
                    second.locator("#ready-button").click()
                    for page in pages:
                        page.locator("#mulligan-button").wait_for(state="visible")
                        assert_game_fits(page)
                    before = snapshot(first, code)
                    for card in before["game"]["players"][0]["hand"][:2]:
                        first.locator(f'#hand [data-card-id="{card["id"]}"]').click()
                    first.locator("#mulligan-button").click()
                    wait_version(second, 0)
                    second.locator("#mulligan-button").click()
                    wait_version(first, 1)
                    wait_version(second, 1)
                    check_fullscreen(first, code, output)
                    first.locator('#journal-button').click()
                    first.locator('#event-log').wait_for(state='visible')
                    first.locator('#close-info').click()
                    first.locator('#own-discard').click()
                    first.locator('#info-dialog').wait_for(state='visible')
                    first.locator('#close-info').click()
                    rng = random.Random(14)
                    moves_used = set()
                    steps = 0
                    while steps < 150:
                        current = snapshot(first, code)
                        game = current["game"]
                        if game["phase"] == "finished":
                            break
                        actor = game["turn"]
                        page = pages[actor]
                        current = snapshot(page, code)
                        moves = [move for move in current["game"]["moves"] if move["type"] != "concede"]
                        choices = [move for move in moves if move["type"] == "choose"]
                        leaders = [move for move in moves if move["type"] == "leader"]
                        playable = [move for move in moves if move["type"] == "play"]
                        passes = [move for move in moves if move["type"] == "pass"]
                        candidates = choices or leaders or (playable if steps < 40 else passes) or passes
                        move = rng.choice(candidates)
                        version = current["game"]["version"]
                        click_move(page, move)
                        for peer in pages:
                            wait_version(peer, version)
                        moves_used.add(move["type"])
                        steps += 1
                        if move['type'] == 'leader' and actor == 0:
                            marker = first.locator('.combat-row.own[data-row="siege"] .leader-standard')
                            marker.wait_for(state='visible')
                            assert marker.locator('svg[data-icon="banner"]').count() == 1
                            assert marker.inner_text() == ''
                            second.locator('.combat-row.enemy[data-row="siege"] .leader-standard').wait_for(state='visible')
                            marker.click()
                            first.locator('#info-dialog').wait_for(state='visible')
                            first.locator('#close-info').click()
                            first.screenshot(path=str(output / 'academy-standard.png'))
                        if steps == 6:
                            first.screenshot(path=str(output / "match.png"), full_page=True)
                            first.locator('#leave-view').click()
                            first.locator('#landing').wait_for(state='visible')
                            assert first.locator('#leave-view').inner_text() == 'Frontiers'
                            first.goto(f"{url}/?room={code}")
                            first.wait_for_selector("#connection.online")
                            assert snapshot(first, code)["me"] == 0
                            first.wait_for_function("version => Number(document.body.dataset.gameVersion) === version", arg=version + 1)
                            for width, height in [(1920, 1080), (1907, 936), (1600, 900), (1366, 768),
                                                  (1280, 720), (1024, 768), (390, 844), (844, 390)]:
                                first.set_viewport_size({"width": width, "height": height})
                                assert_game_fits(first)
                                first.screenshot(path=str(output / f"match-{width}x{height}.png"))
                            first.set_viewport_size({"width": 1440, "height": 1100})
                    final = snapshot(first, code)
                    assert final["game"]["phase"] == "finished", "Match did not finish"
                    for page in pages:
                        page.locator("#match-result").wait_for(state="visible")
                    first.screenshot(path=str(output / "result.png"), full_page=True)
                    for page in pages:
                        page.locator("#ready-button").click()
                    for page in pages:
                        page.locator("#mulligan-button").wait_for(state="visible")
                    assert snapshot(first, code)["game"]["phase"] == "mulligan"
                    first.set_viewport_size({"width": 390, "height": 844})
                    assert_game_fits(first)
                    first.screenshot(path=str(output / "mobile-match.png"), full_page=True)
                    assert first.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflows horizontally"
                    for page in pages:
                        page.locator("#mulligan-button").click()
                    for page in pages:
                        page.wait_for_function("Number(document.body.dataset.gameVersion) === 2")
                    pass_count = 0
                    while snapshot(first, code)["game"]["phase"] != "finished":
                        current = snapshot(first, code)["game"]
                        pages[current["turn"]].locator("#pass-button").click()
                        for page in pages:
                            wait_version(page, current["version"])
                        pass_count += 1
                        assert pass_count <= 4
                    assert snapshot(first, code)["game"]["winner"] is None
                    moves_used.add("pass")
                    mobile = browser.new_context(viewport={"width": 390, "height": 844})
                    mobile_page = mobile.new_page()
                    mobile_page.goto(url)
                    mobile_page.screenshot(path=str(output / "mobile-landing.png"), full_page=True)
                    assert mobile_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    assert not errors, errors
                    print(json.dumps({"browser": browser_channel, "steps": steps,
                                      "rounds": len(final["game"]["history"]),
                                      "actions": sorted(moves_used), "js_errors": errors,
                                      "reconnect": "ok", "rematch": "ok", "mobile": "ok",
                                      "fullscreen": "ok", "ability_icons": len(ability_icons),
                                      "academy_standard": "ok"}, ensure_ascii=False))
                except Exception:
                    for index, page in enumerate(pages):
                        with suppress(Exception):
                            page.screenshot(path=str(output / f"failure-{index}.png"), full_page=True)
                    raise
                finally:
                    browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Browser smoke test for Frontiers")
    parser.add_argument("--browser", default="msedge" if os.name == "nt" else "chromium",
                        choices=["msedge", "chrome", "chromium"])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "browser")
    options = parser.parse_args()
    run(options.browser, options.output)
