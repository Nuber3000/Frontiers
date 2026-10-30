"""Комнаты, сессии, HTTP и WebSocket проверяются через настоящий ASGI-интерфейс."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import unittest

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from frontiers.app import COOKIE, create_app
from frontiers.rooms import RoomStore


class APITests(unittest.TestCase):
    def setUp(self):
        self.store = RoomStore()
        self.app = create_app(self.store, secure_cookies=False)
        self.client = self.enterContext(TestClient(self.app))
        self.tokens = ["a" * 43, "b" * 43, "c" * 43]

    def headers(self, side):
        return {"cookie": f"{COOKIE}={self.tokens[side]}"}

    def request(self, side, method, path, body=None):
        kwargs = {"headers": self.headers(side)}
        if body is not None:
            kwargs["json"] = body
        return self.client.request(method, path, **kwargs)

    def room(self, start=False):
        response = self.request(0, "POST", "/api/rooms", {"name": "Alice"})
        self.assertEqual(response.status_code, 201)
        code = response.json()["code"]
        response = self.request(1, "POST", f"/api/rooms/{code}/join", {"name": "Bob"})
        self.assertEqual(response.status_code, 200)
        if start:
            for side in (0, 1):
                response = self.request(side, "POST", f"/api/rooms/{code}/ready", {})
                self.assertEqual(response.status_code, 200)
        return code

    def snapshot(self, side, code):
        return self.request(side, "GET", f"/api/rooms/{code}").json()

    def test_health_static_and_catalog(self):
        self.assertEqual(self.client.get("/healthz").json()["status"], "ok")
        for path in ("/", "/static/app.js", "/static/scorch.js", "/static/opponent-play.js", "/static/presentation.css", "/static/shiron.css", "/static/styles.css", "/static/match.css",
                     "/static/cards.css", "/static/lobby.css", "/static/artwork.css", "/static/card-art.png", "/static/wood.svg",
                     "/static/decoy.png", "/static/rain.png", "/static/scorch.png",
                     "/static/horn.png", "/static/mushroom.png"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(self.client.get("/api/catalog").json()["faction"], "Королевство Бургундия")

    def test_cookie_is_http_only_and_not_exposed_in_room(self):
        response = self.request(0, "POST", "/api/rooms", {"name": "Alice"})
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertNotIn(self.tokens[0], response.text)
        self.assertNotIn("session", response.json()["seats"][0])

    def test_skone_is_playable_but_its_cards_cannot_enter_burgundy_decks(self):
        from frontiers.catalog import STARTER_DECK, SKONE_CARDS

        catalog = self.client.get("/api/catalog").json()
        self.assertNotIn("forest", catalog["decks"])
        self.assertEqual(catalog["factions"]["skone"]["leader"], "Конунг Ульфрик Синезубый")
        self.assertTrue(catalog["factions"]["skone"]["playable"])
        for card in catalog["cards"]:
            if card["key"] in SKONE_CARDS:
                self.assertEqual(card["faction"], "skone")
                self.assertEqual(card["available"], card["collectible"])
        self.assertEqual(sum(card["available"] and card["faction"] in {"burgundy", "neutral"} for card in catalog["cards"]), 35)
        herald = next(card for card in catalog["cards"] if card["key"] == "herald")
        self.assertEqual(herald["name"], "Габриэль фон Ард")
        self.assertEqual(herald["rows"], ["melee", "ranged"])
        code = self.room()
        for key in SKONE_CARDS:
            with self.subTest(card=key):
                response = self.request(0, "POST", f"/api/rooms/{code}/ready", {"deck": list(STARTER_DECK) + [key]})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(self.snapshot(0, code)["seats"][0]["ready"])

    def test_only_two_players_and_rejoining_restores_same_seat(self):
        code = self.room()
        response = self.request(2, "POST", f"/api/rooms/{code}/join", {"name": "Third"})
        self.assertEqual(response.status_code, 409)
        response = self.request(0, "POST", f"/api/rooms/{code}/join", {"name": "Other name"})
        self.assertEqual(response.json()["me"], 0)
        self.assertEqual(response.json()["seats"][0]["name"], "Alice")

    def test_outsider_cannot_read_ready_or_act(self):
        code = self.room(start=True)
        for method, path, body in [
            ("GET", f"/api/rooms/{code}", None),
            ("POST", f"/api/rooms/{code}/ready", {}),
            ("POST", f"/api/rooms/{code}/actions", {"type": "concede", "version": 0}),
        ]:
            self.assertEqual(self.request(2, method, path, body).status_code, 403)

    def test_ready_starts_match_and_invalid_deck_does_not_ready(self):
        code = self.room()
        response = self.request(0, "POST", f"/api/rooms/{code}/ready", {"deck": ["infantry"] * 22})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.snapshot(0, code)["seats"][0]["ready"])
        self.request(0, "POST", f"/api/rooms/{code}/ready", {})
        self.assertIsNone(self.snapshot(0, code)["game"])
        self.request(1, "POST", f"/api/rooms/{code}/ready", {})
        view = self.snapshot(0, code)["game"]
        self.assertEqual(view["phase"], "mulligan")
        self.assertEqual(len(view["players"][0]["hand"]), 10)
        self.assertNotIn("hand", view["players"][1])

    def test_unknown_input_and_stale_version_rejected(self):
        code = self.room(start=True)
        response = self.request(0, "POST", f"/api/rooms/{code}/actions", {"type": "mulligan", "version": 0, "hacked_score": 999})
        self.assertEqual(response.status_code, 422)
        response = self.request(0, "POST", f"/api/rooms/{code}/actions", {"type": "mulligan", "version": 0})
        self.assertEqual(response.status_code, 200)
        response = self.request(1, "POST", f"/api/rooms/{code}/actions", {"type": "mulligan", "version": 0})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.snapshot(1, code)["game"]["version"], 1)

    def test_simultaneous_duplicate_commands_apply_only_once(self):
        code = self.room(start=True)
        for side in (0, 1):
            current = self.snapshot(side, code)["game"]
            self.request(side, "POST", f"/api/rooms/{code}/actions",
                         {"type": "mulligan", "version": current["version"]})
        game = self.snapshot(0, code)["game"]
        def act():
            return self.request(game["turn"], "POST", f"/api/rooms/{code}/actions",
                                {"type": "pass", "version": game["version"]}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: act(), range(2)))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(self.snapshot(0, code)["game"]["version"], game["version"] + 1)

    def test_foreign_origin_http_and_websocket_rejected(self):
        response = self.client.post("/api/rooms", json={"name": "Alice"}, headers={"origin": "https://evil.invalid"})
        self.assertEqual(response.status_code, 403)
        code = self.room()
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(f"/ws/rooms/{code}", headers={**self.headers(0), "origin": "https://evil.invalid"}):
                pass

    def test_websocket_personal_views_updates_and_stale_error(self):
        code = self.room(start=True)
        path = f"/ws/rooms/{code}"
        with self.client.websocket_connect(path, headers=self.headers(0)) as first:
            first.receive_json()
            with self.client.websocket_connect(path, headers=self.headers(1)) as second:
                state0, state1 = first.receive_json()["state"], second.receive_json()["state"]
                self.assertNotIn("hand", state0["game"]["players"][1])
                self.assertNotIn("hand", state1["game"]["players"][0])
                first.send_json({"type": "mulligan", "version": 0})
                first.receive_json()
                second.receive_json()
                second.send_json({"type": "mulligan", "version": 1})
                state0, state1 = first.receive_json()["state"], second.receive_json()["state"]
                self.assertEqual(state0["game"]["phase"], "playing")
                self.assertEqual(state0["game"]["version"], 2)
                actor = state0["game"]["turn"]
                sender = [first, second][actor]
                sender.send_json({"type": "pass", "version": 2})
                first.receive_json()
                second.receive_json()
                sender.send_json({"type": "pass", "version": 2})
                error = sender.receive_json()
                self.assertEqual(error["type"], "error")
                self.assertEqual(error["state"]["game"]["version"], 3)

    def test_websocket_invalid_message_does_not_break_match(self):
        code = self.room(start=True)
        with self.client.websocket_connect(f"/ws/rooms/{code}", headers=self.headers(0)) as socket:
            socket.receive_json()
            socket.send_text("not-json")
            self.assertEqual(socket.receive_json()["type"], "error")
            socket.send_json({"type": "ping"})
            self.assertEqual(socket.receive_json()["type"], "pong")
            socket.send_json({"type": "mulligan", "version": 0})
            self.assertEqual(socket.receive_json()["state"]["game"]["version"], 1)

    def test_websocket_rejects_outsider(self):
        code = self.room(start=True)
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(f"/ws/rooms/{code}", headers=self.headers(2)):
                pass

    def test_websocket_limits_message_size(self):
        code = self.room(start=True)
        with self.client.websocket_connect(f"/ws/rooms/{code}", headers=self.headers(0)) as socket:
            socket.receive_json()
            socket.send_text("x" * 16385)
            with self.assertRaises(WebSocketDisconnect):
                socket.receive_json()

    def test_disconnect_and_reconnect_preserve_seat(self):
        code = self.room(start=True)
        for _ in range(2):
            with self.client.websocket_connect(f"/ws/rooms/{code}", headers=self.headers(0)) as socket:
                snapshot = socket.receive_json()["state"]
                self.assertEqual(snapshot["me"], 0)
                self.assertEqual(snapshot["game"]["version"], 0)

    def test_rematch_requires_both_players(self):
        code = self.room(start=True)
        first_hand = {card["id"] for card in self.snapshot(0, code)["game"]["players"][0]["hand"]}
        self.request(0, "POST", f"/api/rooms/{code}/actions", {"type": "concede", "version": 0})
        self.request(0, "POST", f"/api/rooms/{code}/ready", {})
        self.assertEqual(self.snapshot(0, code)["game"]["phase"], "finished")
        self.request(1, "POST", f"/api/rooms/{code}/ready", {})
        game = self.snapshot(0, code)["game"]
        self.assertEqual(game["phase"], "mulligan")
        self.assertTrue(first_hand.isdisjoint(card["id"] for card in game["players"][0]["hand"]))

    def test_idle_rooms_expire_and_capacity_is_bounded(self):
        self.store.max_rooms = 1
        code = self.room()
        self.assertEqual(self.request(2, "POST", "/api/rooms", {"name": "Third"}).status_code, 503)
        self.store.rooms[code].touched = time.monotonic() - 4000
        asyncio.run(self.store.cleanup())
        self.assertEqual(self.request(0, "GET", f"/api/rooms/{code}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
