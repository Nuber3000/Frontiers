"""Check streamed music, independent controls and pause/resume without speaker output."""

import asyncio
import socket
import threading
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from frontiers.app import create_app


def run():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(), log_level="error", timeout_graceful_shutdown=2))

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
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.add_init_script("""(() => {
                  if (!localStorage.getItem('frontiers.sound'))
                    localStorage.setItem('frontiers.sound', JSON.stringify({enabled:false,volume:.25}));
                  const NativeAudio = window.Audio;
                  window.musicElements = [];
                  window.Audio = function(...args) {
                    const audio = new NativeAudio(...args);
                    audio.muted = true;
                    musicElements.push(audio);
                    return audio;
                  };
                })();""")
                errors, responses = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: responses.append(response.status)
                        if response.url.endswith("/music-background.ogg") else None)
                page.goto(f"http://127.0.0.1:{port}")
                assert page.evaluate("musicElements.length") == 0
                assert not responses, "Music loaded before user interaction"
                page.locator("#sound-button").click()
                page.wait_for_function("() => musicElements[0]?.currentTime > .1", timeout=15000)
                assert page.evaluate("musicElements[0].loop && musicElements[0].duration > 700")
                expect(page.locator("#music-volume")).to_have_value("20")
                expect(page.locator("#sound-enabled")).not_to_be_checked()

                def volume(value):
                    page.locator("#music-volume").evaluate(
                        "(e,v)=>{e.value=v;e.dispatchEvent(new Event('input'));}", str(value))

                volume(40)
                expect(page.locator("#music-level")).to_have_text("40%")
                assert abs(page.evaluate("musicElements[0].volume") - .1) < .0001
                assert page.evaluate("JSON.parse(localStorage.getItem('frontiers.sound')).volume") == .25
                page.locator("#sound-volume").evaluate(
                    "e=>{e.value=0;e.dispatchEvent(new Event('input'));}")
                assert not page.evaluate("musicElements[0].paused"), "Effect volume muted music"
                volume(0)
                assert page.evaluate("musicElements[0].paused")
                page.reload()
                page.locator("#sound-button").click()
                expect(page.locator("#music-volume")).to_have_value("0")
                assert page.evaluate("musicElements.length") == 0
                volume(40)
                page.wait_for_function("() => musicElements[0]?.currentTime > .1", timeout=15000)
                page.evaluate("""() => {
                  Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
                  document.dispatchEvent(new Event('visibilitychange'));
                }""")
                assert page.evaluate("musicElements[0].paused")
                position = page.evaluate("musicElements[0].currentTime")
                page.evaluate("""() => {
                  Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});
                  document.dispatchEvent(new Event('visibilitychange'));
                }""")
                page.wait_for_function("p=>musicElements[0].currentTime>p", arg=position)
                assert page.evaluate("musicElements.length") == 1
                page.evaluate("musicElements[0].currentTime=musicElements[0].duration-.25")
                page.wait_for_function("() => musicElements[0].currentTime<2 && !musicElements[0].paused", timeout=10000)
                page.locator("#sound-close").click()
                page.locator("#language-button").click()
                page.locator("#sound-button").click()
                expect(page.locator('label[for="music-volume"] span')).to_have_text("Music")
                expect(page.locator("#music-volume")).to_have_value("40")
                assert responses and all(status in (200, 206) for status in responses), responses
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Streamed music, looping, independent volume, persistence, visibility and translation passed.")


if __name__ == "__main__":
    run()
