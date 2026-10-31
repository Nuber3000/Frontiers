"""Run inside the final Docker image, without development/test dependencies."""

import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from frontiers.app import STATIC


assert os.getuid() == 10001
assert not Path("/app/src").exists(), "Runtime contains a second source copy"
assert shutil.which("uv") is None, "Build tooling leaked into runtime"
webp_count = len(list(STATIC.glob("*.webp")))
assert (STATIC / "ting.webp").is_file()
assert not list(STATIC.glob("*.png"))

base = "http://127.0.0.1:8000"
server = subprocess.Popen([sys.executable, "-m", "frontiers", "--host", "127.0.0.1", "--port", "8000"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    for attempt in range(100):
        try:
            with urllib.request.urlopen(base + "/healthz", timeout=1) as response:
                assert json.load(response)["status"] == "ok"
            break
        except (urllib.error.URLError, TimeoutError):
            if server.poll() is not None:
                raise RuntimeError(server.stderr.read().decode())
            time.sleep(.1)
    else:
        raise RuntimeError("Runtime did not become healthy")
    with urllib.request.urlopen(base + "/api/catalog") as response:
        catalog = json.load(response)
    for path, mime in [("/", "text/html"), ("/static/local-profile.js", "javascript"),
                       ("/static/scorch.webp", "image/webp"), ("/static/valknut.svg", "image/svg+xml")]:
        with urllib.request.urlopen(base + path) as response:
            assert mime in response.headers["Content-Type"], (path, response.headers["Content-Type"])
    for key, leader in catalog["leaders"].items():
        with urllib.request.urlopen(base + "/static/" + leader.get("portrait", f"leader_{key}.webp")) as response:
            assert response.headers["Content-Type"] == "image/webp"
    clients = [urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())) for _ in range(2)]

    def post(client, path, data):
        request = urllib.request.Request(base + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
        with client.open(request) as response:
            return json.load(response)

    room = post(clients[0], "/api/rooms", {"name": "Runtime A"})
    code = room["code"]
    post(clients[1], f"/api/rooms/{code}/join", {"name": "Runtime B"})
    for client in clients:
        room = post(client, f"/api/rooms/{code}/ready", {"leader": room["my_leader"], "deck": room["my_deck"], "ready": True})
    assert room["game"]["phase"] == "mulligan"
    print(json.dumps({"runtime": "healthy", "uid": os.getuid(), "webp": webp_count,
                      "static_bytes": sum(path.stat().st_size for path in STATIC.iterdir() if path.is_file()),
                      "all_leader_assets": "ok", "two_player_match": "ok", "no_duplicate_source": True}))
finally:
    server.terminate()
    server.wait(timeout=10)
