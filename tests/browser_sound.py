"""Render synthesized sounds and check browser settings and event deduplication."""

import asyncio
import socket
import threading
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from frontiers.app import create_app
from test_engine import fixture, put


# Use the browser's real audio renderer, with output kept in an in-memory buffer.
# No test sound is sent to the user's speakers.
AUDIO_RENDERER = """(() => {
  const preferences = JSON.parse(localStorage.getItem('frontiers.sound')) || {};
  preferences.musicVolume = 0;
  localStorage.setItem('frontiers.sound', JSON.stringify(preferences));
  window.audioNodesStarted = 0;
  window.audioContextsCreated = 0;
  window.audioSamplesDecoded = 0;
  window.audioBufferEvents = [];
  window.AudioContext = class extends OfflineAudioContext {
    constructor() {
      super(1, 384000, 48000);
      window.renderContext = this;
      window.audioContextsCreated++;
    }
    get state() { return 'running'; }
    async decodeAudioData(bytes) {
      const buffer = await super.decodeAudioData(bytes);
      window.audioSamplesDecoded++;
      return buffer;
    }
    createOscillator() {
      const source = super.createOscillator();
      const start = source.start.bind(source);
      source.start = (...args) => { window.audioNodesStarted++; return start(...args); };
      return source;
    }
    createBufferSource() {
      const source = super.createBufferSource();
      const start = source.start.bind(source);
      const stop = source.stop.bind(source);
      let event;
      source.start = (...args) => {
        window.audioNodesStarted++;
        event = {stage:document.querySelector('#opponent-play')?.dataset.stage,
          tableBurns:document.querySelectorAll('.scorch-burn').length,
          duration:source.buffer?.duration,
          at:performance.now(), audioStart:args[0] || 0};
        window.audioBufferEvents.push(event);
        return start(...args);
      };
      source.stop = (...args) => { if(event) event.audioStop=args[0]; return stop(...args); };
      return source;
    }
  };
})();"""


def run():
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
                page = browser.new_page(locale="ru-RU", viewport={"width": 1280, "height": 720})
                page.add_init_script(AUDIO_RENDERER)
                errors, audio_requests = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: audio_requests.append(request.url)
                        if request.url.endswith((".mp3", ".wav", ".ogg", ".webm")) else None)
                url = f"http://127.0.0.1:{port}"
                page.goto(url)
                expect(page.locator("#play-bot")).to_be_enabled()
                assert page.evaluate("audioContextsCreated") == 0, "Audio initialized without a gesture"
                page.locator("#sound-button").click()
                expect(page.locator("#sound-dialog")).to_be_visible()
                page.locator("#sound-preview").click()
                signal = page.evaluate("""async () => {
                  const buffer = await renderContext.startRendering();
                  const data = buffer.getChannelData(0);
                  return {peak: data.reduce((peak, v) => Math.max(peak, Math.abs(v)), 0),
                    energy: data.reduce((sum, v) => sum + v*v, 0)};
                }""")
                assert .001 < signal["peak"] < 1 and signal["energy"] > .001, signal
                page.locator("#sound-volume").evaluate("""e => {
                  e.value = '60'; e.dispatchEvent(new Event('input', {bubbles:true}));
                }""")
                expect(page.locator("#sound-level")).to_have_text("60%")
                page.locator("#sound-enabled").uncheck()
                count = page.evaluate("audioNodesStarted")
                page.evaluate("FrontiersAudio.play('victory')")
                assert page.evaluate("audioNodesStarted") == count, "Muted sound generated audio"
                page.reload()
                assert page.evaluate("audioContextsCreated") == 0
                page.locator("#language-button").click()
                expect(page.locator("#sound-button")).to_have_attribute("aria-label", "Sound settings")
                page.locator("#sound-button").click()
                expect(page.locator("#sound-enabled")).not_to_be_checked()
                expect(page.locator("#sound-volume")).to_have_value("60")
                page.locator("#sound-enabled").check()
                page.locator("#sound-volume").evaluate("e => { e.value='0'; e.dispatchEvent(new Event('input')); }")
                count = page.evaluate("audioNodesStarted")
                page.evaluate("FrontiersAudio.play('scorch')")
                assert page.evaluate("audioNodesStarted") == count, "Zero-volume sound generated audio"
                page.locator("#sound-volume").evaluate("e => { e.value='25'; e.dispatchEvent(new Event('input')); }")
                # A first snapshot is silent. A new action sounds once. A duplicate,
                # a version jump after reconnect and an old result remain silent.
                page.evaluate("""() => {
                  const player = () => ({leader_used:false, mulligan_done:true, hand:[]});
                  window.beforeSound = {code:'ROOM', me:0, game:{match_id:'test', version:0,
                    phase:'playing', players:[player(), player()], scorched:[]}};
                  window.nextSound = structuredClone(beforeSound);
                  nextSound.game.version = 1; nextSound.game.played = {card:{key:'knight'}};
                  FrontiersAudio.observe(null, beforeSound);
                }""")
                count = page.evaluate("audioNodesStarted")
                page.evaluate("FrontiersAudio.observe(beforeSound, nextSound)")
                sounded = page.evaluate("audioNodesStarted")
                assert sounded > count
                page.evaluate("FrontiersAudio.observe(beforeSound, nextSound)")
                assert page.evaluate("audioNodesStarted") == sounded, "Duplicate snapshot repeated sound"
                page.evaluate("nextSound.game.version=5; FrontiersAudio.observe(beforeSound,nextSound)")
                assert page.evaluate("audioNodesStarted") == sounded, "Reconnect replayed old sounds"
                page.evaluate("FrontiersAudio.result('unknown','victory')")
                assert page.evaluate("audioNodesStarted") == sounded, "Old result replayed its fanfare"
                page.wait_for_function("() => audioSamplesDecoded === 13")
                # Card effects and matching leaders use the supplied recordings.
                for key, ability, seconds in (("horn", None, 4.6), ("frost", None, 1.74), ("clear", None, 3.13), ("fog", None, 2.90065),
                                             ("storm", None, 3.14392), ("rain", None, 3.14392), ("banner", "horn", 4.6)):
                    event = page.evaluate("""([key,ability]) => {
                      const before=structuredClone(beforeSound), next=structuredClone(before);
                      before.game.match_id=next.game.match_id='sample-'+key;
                      next.game.version=1;next.game.played={card:{key,abilities:ability?[ability]:[]}};
                      FrontiersAudio.observe(null,before);window.audioBufferEvents=[];
                      FrontiersAudio.observe(before,next);FrontiersAudio.observe(before,next);
                      return audioBufferEvents;
                    }""", [key, ability])
                    assert len(event) == 1 and abs(event[0]["duration"] - seconds) < .002, (key, event)
                for leader, seconds in (("academy", 4.6), ("ellifarn_aim", 4.6), ("skone_horn", 4.6),
                                        ("fog", 2.90065), ("skone_storm", 3.14392), ("shiron_rain", 3.14392), ("sun", 3.13)):
                    event = page.evaluate("""leader => {
                      const before=structuredClone(beforeSound),next=structuredClone(before);
                      before.game.match_id=next.game.match_id='leader-'+leader;
                      next.game.version=1;next.game.players[1].leader=leader;next.game.players[1].leader_used=true;
                      FrontiersAudio.observe(null,before);window.audioBufferEvents=[];
                      FrontiersAudio.observe(before,next);return audioBufferEvents;
                    }""", leader)
                    assert len(event) == 1 and abs(event[0]["duration"] - seconds) < .002, (leader, event)
                page.locator("#sound-close").click()

                # A preview reveals the card first. Fire must start on the first
                # burning frame, then stay silent when the table state commits.
                page.reload()
                page.locator("#sound-button").click()
                page.wait_for_function("() => audioSamplesDecoded === 13")
                page.locator("#sound-close").click()
                page.evaluate("""() => {
                  const player=()=>({leader_used:false,mulligan_done:true,hand:[]});
                  const before={code:'PREVIEW',me:0,game:{match_id:'preview-test',version:0,
                    phase:'playing',players:[player(),player()],scorched:[]}};
                  const next=structuredClone(before); next.game.version=1;
                  next.game.played={card:{key:'scorch'}}; next.game.scorched=['victim'];
                  FrontiersAudio.observe(null,before);
                  const card=document.createElement('button');card.className='card special';
                  card.dataset.cardId='preview-scorch';card.innerHTML='<span class="card-art art-scorch"></span>';
                  window.soundPreview=new FrontiersOpponentPlay();
                  window.audioBufferEvents=[];window.previewCommitted=false;
                  window.previewFinished=soundPreview.play(card,{scorch:true,
                    onBurn:duration=>FrontiersAudio.burn(next.game.match_id,next.game.version,duration,'preview'),
                    commit:()=>{FrontiersAudio.observe(before,next);window.previewCommitted=true;},
                    destination:()=>null});
                }""")
                page.wait_for_timeout(150)
                assert page.evaluate("audioBufferEvents.length") == 0, "Fire played during card reveal"
                page.wait_for_function("() => audioBufferEvents.length === 1")
                fire_event = page.evaluate("audioBufferEvents[0]")
                assert fire_event["stage"] == "burn", fire_event
                assert abs(fire_event["audioStop"] - fire_event["audioStart"] - .9) < .01, fire_event
                page.wait_for_function("() => previewCommitted")
                page.locator("#opponent-play").wait_for(state="detached")
                assert page.evaluate("audioBufferEvents.length") == 1, "Table commit repeated the fire sound"

                # Real clients must each hear the actual table burn; the opponent
                # also hears the earlier burn of the played Scorch card.
                created = page.request.post(url + "/api/rooms", data={"name": "Actor"}).json()
                code = created["code"]
                other = browser.new_page(locale="ru-RU", viewport={"width": 1280, "height": 720})
                other.add_init_script(AUDIO_RENDERER)
                other.on("pageerror", lambda error: errors.append(str(error)))
                other.request.post(url + f"/api/rooms/{code}/join", data={"name": "Opponent"})
                room = app.state.rooms.rooms[code]
                room.game = fixture(["scorch", "knight"], ["knight"])
                put(room.game, 0, "knight")
                put(room.game, 1, "knight")
                room.changed()
                for client in (page, other):
                    client.goto(url + f"/?room={code}")
                    expect(client.locator("#arena")).to_be_visible()
                    client.locator("#sound-button").click()
                    client.wait_for_function("() => audioSamplesDecoded === 13")
                    client.locator("#sound-close").click()
                    client.evaluate("audioBufferEvents=[]")
                page.locator('#hand [data-card-key="scorch"]').click()
                page.locator("#selection-info .primary").click()
                page.wait_for_function("() => audioBufferEvents.length === 1")
                other.wait_for_function("() => audioBufferEvents.length === 2")
                own_events = page.evaluate("audioBufferEvents")
                other_events = other.evaluate("audioBufferEvents")
                assert own_events[0]["tableBurns"] == 2, own_events
                assert other_events[0]["stage"] == "burn" and other_events[0]["tableBurns"] == 0, other_events
                assert other_events[1]["tableBurns"] == 2 and not other_events[1].get("stage"), other_events
                assert other_events[1]["at"] - other_events[0]["at"] >= 750, other_events
                other.locator('#hand [data-card-key="knight"]').click()
                assert other.evaluate("audioBufferEvents.length") == 2, "Rerender repeated table sound"
                other.close()
                page.evaluate("localStorage.removeItem('frontiers.room')")
                page.goto(url)

                # Render every effect independently at maximum volume and ensure
                # finite, non-silent samples without clipping or runaway tails.
                levels = {}
                for kind in ("select", "card", "shuffle", "leader", "scorch", "pass", "turn",
                             "round-win", "round-loss", "round-draw", "victory", "defeat", "draw", "horn", "frost", "fog", "storm", "clear"):
                    page.reload()
                    page.locator("#sound-button").click()
                    page.wait_for_function("() => audioSamplesDecoded === 13")
                    page.locator("#sound-volume").evaluate("e => { e.value='100'; e.dispatchEvent(new Event('input')); }")
                    signal = page.evaluate("""async kind => {
                      FrontiersAudio.play(kind);
                      const buffer = await renderContext.startRendering(), samples = buffer.getChannelData(0);
                      let energy=0, loudness=0;
                      for(let i=0;i<samples.length;i++) {
                        energy+=samples[i]*samples[i];
                        if(i>=4800) energy-=samples[i-4800]**2;
                        loudness=Math.max(loudness,Math.sqrt(Math.max(0,energy)/4800));
                      }
                      return {peak:samples.reduce((p,v) => Math.max(p, Math.abs(v)),0), loudness,
                        tail:samples.slice(-4800).some(v => Math.abs(v) > .0001)};
                    }""", kind)
                    assert .0001 < signal["peak"] < .9 and not signal["tail"], (kind, signal)
                    levels[kind] = signal
                assert levels["scorch"]["loudness"] <= levels["card"]["loudness"] * 1.25, levels
                assert levels["scorch"]["peak"] <= levels["card"]["peak"] * 1.25, levels
                assert not errors, errors
                expected_files = {"scorch-fire.ogg", "sound-horn.ogg", "sound-frost.ogg", "sound-fog.ogg", "sound-storm.ogg", "sound-clear.ogg", "sound-turn.ogg", "sound-round-win.ogg", "sound-round-loss.ogg", "sound-round-draw.ogg", "sound-draw.ogg", "sound-victory.ogg", "sound-defeat.ogg"}
                assert {url.rsplit("/", 1)[-1] for url in audio_requests} == expected_files, audio_requests
                browser.close()
        finally:
            server.should_exit = True
            thread.join(5)
    print("Sound rendering, volume, mute, saved preferences, translations and deduplication passed.")


if __name__ == "__main__":
    run()
