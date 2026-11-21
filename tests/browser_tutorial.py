"""Verify local lessons on the real arena, including offline play and effects."""
import argparse
import asyncio
from pathlib import Path
import re
import socket
import threading
import time

import uvicorn
from playwright.sync_api import expect, sync_playwright

from frontiers.app import create_app
from frontiers.tutorial import LESSONS


def complete_deck_tour(page, output, language, mobile=False):
    overlay = page.locator("#deck-tutorial-overlay")
    expect(page.locator("#lobby")).to_be_visible()
    expect(page.locator("#tutorial-dialog")).to_be_hidden()
    expect(overlay).to_have_attribute("data-step", "0")
    expect(page.locator("#ready-button")).to_be_disabled()
    saved = page.evaluate("Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('frontiers.profile.v1.')))")
    page.locator("#deck-tutorial-next").click()
    expect(overlay).to_have_attribute("data-step", "1")
    expect(page.locator("#deck-tutorial-next")).to_be_hidden()
    # Selecting the same faction, or attempting to change the leader early,
    # must not satisfy the faction task.
    initial_faction = page.locator("#faction-select").input_value()
    page.locator("#faction-select").select_option(initial_faction)
    expect(overlay).to_have_attribute("data-step", "1")
    initial_leader = page.locator("#leader-select").input_value()
    other_leader = page.locator("#leader-select option").evaluate_all("options => options.find(option => !option.selected).value")
    page.locator("#leader-select").select_option(other_leader)
    expect(page.locator("#leader-select")).to_have_value(initial_leader)
    expect(overlay).to_have_attribute("data-step", "1")
    if not mobile:
        page.screenshot(path=str(output / f"deck-faction-{language}.png"))
    page.locator("#faction-select").select_option("udul")
    expect(overlay).to_have_attribute("data-step", "2")
    expect(page.locator("#ready-button")).to_be_disabled()
    leader = page.locator("#leader-select").input_value()
    page.locator("#leader-select").select_option(leader)
    expect(overlay).to_have_attribute("data-step", "2")
    other = page.locator("#leader-select option").evaluate_all("options => options.find(option => !option.selected).value")
    page.locator("#leader-select").select_option(other)
    expect(overlay).to_have_attribute("data-step", "3")
    before = int(page.locator("#deck-stats dd").first.inner_text())
    target = page.locator('#collection .collection-item .card-adjust button:not(:disabled)').first
    key = target.evaluate("button => button.closest('.collection-item').querySelector('.card').dataset.cardKey")
    # Screenshots and bounds checks run after the spotlight has followed scrolling.
    page.wait_for_function("document.querySelector('#deck-tutorial-focus').getBoundingClientRect().height > 20")
    page.screenshot(path=str(output / f"deck-add-{'mobile-' if mobile else ''}{language}.png"))
    coach = page.locator("#deck-tutorial-coach").bounding_box()
    viewport = page.viewport_size
    assert 0 <= coach["x"] and coach["x"] + coach["width"] <= viewport["width"], coach
    assert 0 <= coach["y"] and coach["y"] + coach["height"] <= viewport["height"], coach
    target.click()
    expect(overlay).to_have_attribute("data-step", "4")
    assert int(page.locator("#deck-stats dd").first.inner_text()) == before + 1
    expect(page.locator("#deck-tutorial-next")).to_be_hidden()
    expect(page.locator("#ready-button")).to_be_disabled()
    page.locator(f'#deck-cards .collection-item:has([data-card-key="{key}"]) .card-adjust button').click()
    expect(overlay).to_have_attribute("data-step", "5")
    assert int(page.locator("#deck-stats dd").first.inner_text()) == before
    text = page.locator("#deck-tutorial-text").inner_text()
    assert "22" in text and "10" in text
    if language == "en":
        assert not re.search(r"[А-Яа-яЁё]", page.locator("#deck-tutorial-coach").inner_text())
    else:
        assert "шанс" in text and "При увеличении числа карт в колоде," in text
    assert saved == page.evaluate("Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('frontiers.profile.v1.')))")
    page.locator("#deck-tutorial-next").click()


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    app = create_app()
    hold_rules, requested = threading.Event(), threading.Event()

    @app.middleware("http")
    async def delay_rules(request, call_next):
        if request.url.path == "/api/local-engine" and hold_rules.is_set():
            requested.set()
            while hold_rules.is_set():
                await asyncio.sleep(.02)
        return await call_next(request)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
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
                    raise RuntimeError("Tutorial test server did not start")
                time.sleep(.05)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge")
                context = browser.new_context(locale="ru-RU", viewport={"width":1366,"height":768})
                page = context.new_page()
                errors, commands, sockets = [], [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: commands.append(request.url) if
                        request.method == "POST" or "/api/tutorials" in request.url else None)
                page.on("websocket", lambda ws: sockets.append(ws.url))
                page.goto(url)
                expect(page.locator("#online-rooms")).to_have_text("Комнат в сети: 0")
                expect(page.locator("#tutorial-button")).to_be_enabled()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                page.locator("#find-match").click()
                expect(page.locator("#tutorial-offer-dialog")).to_be_visible()
                expect(page.locator("#entry-form #tutorial-button")).to_have_count(0)
                expect(page.locator("#rules-button")).to_have_text("Обучение")
                page.screenshot(path=str(output / "first-visit-offer-ru.png"))
                page.evaluate("""() => {
                    window.observedSounds = []; window.weatherUpdates = 0;
                    const audio = FrontiersAudio.observe;
                    FrontiersAudio.observe = (previous, next) => {
                        if (previous?.game && next.game && next.game.version === previous.game.version + 1)
                            observedSounds.push(next.game.played?.card?.key || (next.game.leader_played != null ? 'leader' : 'pass'));
                        return audio(previous, next);
                    };
                    const weather = FrontiersWeather.prototype.observe;
                    FrontiersWeather.prototype.observe = function (...args) {
                        weatherUpdates++; return weather.apply(this, args);
                    };
                }""")
                # Cancel a slow first download, then launch a fresh worker.
                hold_rules.set()
                page.locator("#tutorial-offer-start").click()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                complete_deck_tour(page, output, "ru")
                expect(page.locator("#tutorial-loading")).to_be_visible()
                deadline = time.monotonic() + 10
                while not requested.is_set() and time.monotonic() < deadline:
                    page.wait_for_timeout(50)
                assert requested.is_set()
                page.locator("#tutorial-close").click()
                expect(page.locator("#tutorial-dialog")).to_be_hidden()
                expect(page.locator("#deck-tutorial-coach")).to_be_visible()
                page.locator("#deck-tutorial-exit").click()
                expect(page.locator("#landing")).to_be_visible()
                hold_rules.clear()
                for language in ("ru", "en"):
                    if language == "en":
                        page.locator("#language-button").click()
                    page.locator("#rules-button").click()
                    expect(page.locator("#rules-dialog")).to_be_visible()
                    expect(page.locator("#rules-dialog #tutorial-button")).to_have_text("Начать обучение" if language == "ru" else "Start tutorial")
                    page.screenshot(path=str(output / f"training-section-{language}.png"))
                    page.locator("#tutorial-button").click()
                    expect(page.locator("#rules-dialog")).to_be_hidden()
                    if language == "en":
                        page.set_viewport_size({"width":390,"height":844})
                    complete_deck_tour(page, output, language, mobile=language == "en")
                    page.set_viewport_size({"width":390,"height":844} if language == "en" else {"width":1366,"height":768})
                    expect(page.locator("#arena")).to_be_visible(timeout=30000)
                    expect(page.locator("#tutorial-lesson, #tutorial-menu")).to_have_count(0)
                    for lesson_index, (lesson, spec) in enumerate(LESSONS.items()):
                        if lesson_index:
                            page.locator("#tutorial-next").click()
                        expected_title = page.evaluate("title => FrontiersI18n.t(title)", spec["title"])
                        expect(page.locator("#tutorial-scenario-title")).to_have_text(expected_title)
                        expect(page.locator("#tutorial-guide")).to_be_visible()
                        expect(page.locator("#tutorial-next")).to_be_hidden()
                        expect(page.locator("#tutorial-scenario-progress")).to_have_text(
                            f"Сценарий {lesson_index+1} из 5" if language == "ru" else f"Scenario {lesson_index+1} of 5")
                        expect(page.locator("#arena")).to_be_visible()
                        expect(page.locator("body")).to_have_class(re.compile(r"in-tutorial"))
                        expect(page.locator("#arena .combat-row")).to_have_count(6)
                        expect(page.locator("#tutorial-restart")).to_be_enabled()
                        if language == "en":
                            context.set_offline(True)
                        if lesson == "rows":
                            page.locator('#hand [data-card-key="knight"]').evaluate("element => window.knight = element")
                        for index, (_, kind, key) in enumerate(spec["steps"]):
                            if language == "ru" and ((lesson == "boosts" and index == 2) or lesson == "abilities"):
                                page.set_viewport_size({"width":1920,"height":940})
                                if lesson == "boosts":
                                    page.wait_for_function("""() => {
                                        const guide = document.querySelector('#tutorial-guide').getBoundingClientRect();
                                        return Math.abs(guide.x + guide.width / 2 - innerWidth / 2) < 1
                                            && guide.y + guide.height / 2 < innerHeight / 2 - 50
                                            && guide.bottom <= document.querySelector('.combat-row.own[data-row="siege"]').getBoundingClientRect().top - 12;
                                    }""")
                                    # The two ballistas and the banner slot must remain visible.
                                    assert page.locator('.combat-row.own[data-row="siege"] .card').evaluate_all("""cards => {
                                        const hint = document.querySelector('#tutorial-guide').getBoundingClientRect();
                                        return cards.every(card => {
                                            const box = card.getBoundingClientRect();
                                            return box.right <= hint.left || box.left >= hint.right || box.bottom <= hint.top || box.top >= hint.bottom;
                                        });
                                    }""")
                                    page.screenshot(path=str(output / "boosts-step-three-centered.png"))
                                elif kind != "choose":
                                    page.wait_for_function("""() => {
                                        const guide = document.querySelector('#tutorial-guide').getBoundingClientRect();
                                        const row = document.querySelector('.combat-row.own[data-row="melee"]').getBoundingClientRect();
                                        return Math.abs(innerWidth - guide.right - 12) < 1
                                            && Math.abs(guide.y + guide.height / 2 - row.y - row.height / 2) < 1;
                                    }""")
                                    page.screenshot(path=str(output / f"abilities-step-{index+1}-right.png"))
                            if kind == "play":
                                page.locator(f'#hand [data-card-key="{key}"]').first.click()
                                if key == "horn":
                                    page.locator('.combat-row.own[data-row="siege"] .row-special.slot-droppable').click()
                                else:
                                    page.locator("#selection-info .primary").click()
                            elif kind == "leader":
                                page.locator("#leader-button").click()
                                expect(page.locator("#leader-dialog")).to_be_visible()
                                expect(page.locator("#leader-dialog #tutorial-guide")).to_be_visible()
                                page.screenshot(path=str(output / f"leader-guidance-{language}.png"))
                                page.locator("#leader-apply").click()
                            elif kind == "pass":
                                page.locator("#pass-button").click()
                            else:
                                expect(page.locator("#choice-dialog #tutorial-guide")).to_be_visible()
                                page.screenshot(path=str(output / f"medic-guidance-{language}.png"))
                                page.locator(f'#choice-cards [data-card-key="{key}"]').click()
                            if index + 1 == len(spec["steps"]):
                                expect(page.locator("#tutorial-next")).to_be_visible()
                            else:
                                expect(page.locator("#tutorial-progress")).to_have_text(
                                    f"Шаг {index+2} из {len(spec['steps'])}" if language == "ru"
                                    else f"Step {index+2} of {len(spec['steps'])}")
                            if lesson == "weather" and index == 0:
                                expect(page.locator("#weather-effects")).to_be_visible()
                                expect(page.locator(".combat-row.weathered")).to_have_count(2)
                                # Restart the current lesson without advancing the sequence.
                                page.locator("#tutorial-restart").click()
                                expect(page.locator("#weather-strip")).to_be_empty()
                                expect(page.locator("#tutorial-next")).to_be_hidden()
                                expect(page.locator("#tutorial-progress")).to_have_text("Шаг 1 из 2" if language == "ru" else "Step 1 of 2")
                                page.locator('#hand [data-card-key="frost"]').click()
                                page.locator("#selection-info .primary").click()
                                expect(page.locator(".combat-row.weathered")).to_have_count(2)
                            if lesson == "weather" and index == 1:
                                expect(page.locator("#weather-effects")).to_have_attribute("data-clearing", "true")
                        if lesson == "rows":
                            assert page.locator('.combat-row.own [data-card-key="knight"]').evaluate("element => element === window.knight")
                            page.set_viewport_size({"width":390,"height":844})
                            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                            for selector in ("#tutorial-guide", "#arena", "#hand"):
                                bounds = page.locator(selector).bounding_box()
                                assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 845, (selector, bounds)
                            page.screenshot(path=str(output / f"arena-mobile-{language}.png"))
                            if language == "ru":
                                page.set_viewport_size({"width":1366,"height":768})
                        if lesson == "boosts":
                            page.screenshot(path=str(output / f"arena-{language}.png"))
                        if language == "en":
                            assert not re.search(r"[А-Яа-яЁё]", page.locator("#tutorial-guide").inner_text())
                            assert not re.search(r"[А-Яа-яЁё]", page.locator("#my-score").inner_text())
                            assert not re.search(r"[А-Яа-яЁё]", page.locator("#opponent-score").inner_text())
                        assert not app.state.rooms.rooms
                    page.locator("#tutorial-next").click()
                    expect(page.locator("#landing")).to_be_visible()
                    context.set_offline(False)
                observed = page.evaluate("observedSounds")
                weather_updates = page.evaluate("weatherUpdates")
                # Existing history suppresses the offer; clearing it offers training again.
                page.evaluate("""() => localStorage.setItem('frontiers.profile.v1.history', JSON.stringify([
                    {id:'existing-match', finishedAt:Date.now(), outcome:'victory',
                     players:[{name:'A',faction:'burgundy'},{name:'B',faction:'burgundy'}], rounds:[]}
                ]))""")
                page.reload()
                expect(page.locator("#tutorial-button")).to_be_enabled()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                page.locator("#rules-button").click()
                expect(page.locator("#rules-dialog")).to_be_visible()
                page.locator("#rules-close").click()
                page.evaluate("localStorage.removeItem('frontiers.profile.v1.history')")
                page.reload()
                expect(page.locator("#tutorial-button")).to_be_enabled()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                page.locator("#create-room").click()
                expect(page.locator("#tutorial-offer-dialog")).to_be_visible()
                expect(page.locator("#tutorial-offer-start")).to_have_text("Start tutorial")
                assert not re.search(r"[А-Яа-яЁё]", page.locator("#tutorial-offer-dialog").inner_text())
                page.screenshot(path=str(output / "first-visit-offer-mobile-en.png"))
                page.locator("#tutorial-offer-later").click()
                expect(page.locator("#tutorial-offer-dialog")).to_be_hidden()
                expect(page.locator("#player-name")).to_be_editable()
                assert not commands, commands
                assert not sockets, sockets
                assert not errors, errors
                assert {"knight", "scout", "frost", "leader", "horn", "spy_scribe", "field_medic", "pass"} <= set(observed), observed
                assert weather_updates > 10
                assert page.evaluate("JSON.parse(localStorage.getItem('frontiers.profile.v1.history') || '[]').length") == 0
                browser.close()
        finally:
            hold_rules.clear()
            server.should_exit = True
            thread.join(5)
    print("The deck tour and five lessons passed in order with desktop/mobile coach marks, native leader/medic dialogs, RU/EN, offline play, weather, audio observations, restart and cancellation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/browser/tutorial"))
    run(parser.parse_args().output)
