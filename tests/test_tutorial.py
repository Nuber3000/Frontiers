import json
import unittest

from fastapi.testclient import TestClient

from frontiers.app import create_app
from frontiers.local_match import LocalMatch
from frontiers.rooms import RoomStore
from frontiers.tutorial import LESSONS


class TutorialTests(unittest.TestCase):
    def setUp(self):
        self.match = LocalMatch()

    def dispatch(self, **request):
        return json.loads(self.match.dispatch(json.dumps(request)))

    def start(self, lesson):
        result = self.dispatch(type="tutorial-start", lesson=lesson)
        self.assertNotIn("error", result)
        self.assertFalse(result["bot_turn"])
        self.assertIsNone(self.match.room)
        return result["state"]

    def advance(self, state):
        move = state["game"]["moves"][0]
        result = self.dispatch(type="action", action=move, version=state["game"]["version"])
        self.assertNotIn("error", result)
        self.assertFalse(result["bot_turn"])
        return result["state"]

    def test_each_lesson_uses_real_rules_and_finishes_locally(self):
        self.assertEqual(len(self.dispatch(type="tutorial-list")["lessons"]), 5)
        for lesson in LESSONS:
            with self.subTest(lesson=lesson):
                state = self.start(lesson)
                while not state["tutorial"]["complete"]:
                    if lesson == "weather" and state["tutorial"]["step"] == 1:
                        players = state["game"]["players"]
                        self.assertEqual(players[0]["score"], 1)
                        self.assertEqual({card["key"]: card["strength"] for card in players[1]["board"]},
                                         {"knight": 1, "regent": 10, "watchman": 0})
                    previous = state
                    state = self.advance(state)
                    self.assertEqual(state["game"]["version"], previous["game"]["version"] + 1)
                    self.assertEqual(state["game"]["match_id"], previous["game"]["match_id"])
                self.assertEqual(state["tutorial"]["step"], len(LESSONS[lesson]["steps"]))
                self.assertEqual(state["game"]["moves"], [])
                players = state["game"]["players"]
                if lesson == "rows":
                    self.assertEqual(players[0]["score"], 9)
                elif lesson == "weather":
                    self.assertFalse(state["game"]["weather"])
                    self.assertTrue(players[0]["leader_used"])
                elif lesson == "boosts":
                    self.assertEqual(players[0]["score"], 64)
                elif lesson == "abilities":
                    self.assertEqual(len(players[0]["hand"]), 3)
                    self.assertIn("spy_scribe", [card["key"] for card in players[1]["board"]])
                    self.assertIn("blue_guard", [card["key"] for card in players[0]["board"]])
                    self.assertEqual([card["key"] for card in players[0]["discard"]], ["regent"])
                elif lesson == "rounds":
                    self.assertEqual(players[0]["lives"], 1)
                    self.assertEqual(len(players[0]["hand"]), 3)
                    self.assertEqual(state["game"]["round"], 2)

    def test_invalid_stale_and_duplicate_actions_preserve_progress(self):
        state = self.start("rows")
        clear = next(card for card in state["game"]["players"][0]["hand"] if card["key"] == "clear")
        self.assertIn("error", self.dispatch(type="action", action={"type": "play", "card_id": clear["id"]}, version=0))
        self.assertEqual(json.loads(json.dumps(self.match.tutorial.view())), state)
        move = state["game"]["moves"][0]
        self.assertIn("error", self.dispatch(type="action", action=move, version=7))
        self.assertEqual(json.loads(json.dumps(self.match.tutorial.view())), state)
        state = self.advance(state)
        self.assertIn("error", self.dispatch(type="action", action=move, version=0))
        self.assertEqual(json.loads(json.dumps(self.match.tutorial.view())), state)
        self.assertIn("error", self.dispatch(type="tutorial-start", lesson="missing"))
        self.assertEqual(json.loads(json.dumps(self.match.tutorial.view())), state)
        restarted = self.start("rows")
        self.assertEqual(restarted["tutorial"]["step"], 0)
        self.assertNotEqual(restarted["game"]["match_id"], state["game"]["match_id"])
        self.assertNotIn("error", self.dispatch(type="create", name="Player"))
        self.assertIsNone(self.match.tutorial)

    def test_rules_bundle_includes_training_without_server_gameplay_api(self):
        store = RoomStore()
        with TestClient(create_app(store, secure_cookies=False)) as client:
            self.assertIn("tutorial.py", client.get("/api/local-engine").json())
            self.assertEqual(client.get("/api/tutorials").status_code, 404)
            self.start("boosts")
            self.assertFalse(store.rooms)

    def test_public_counter_counts_online_rooms_once(self):
        with TestClient(create_app(secure_cookies=False)) as client:
            stats = client.get("/api/stats")
            self.assertEqual(stats.json(), {"online_rooms": 0})
            self.assertEqual(stats.headers["cache-control"], "no-store")
            self.assertNotIn("set-cookie", stats.headers)
            code = client.post("/api/rooms", json={"name": "Host"}).json()["code"]
            self.assertEqual(client.get("/api/stats").json()["online_rooms"], 0)
            with client.websocket_connect(f"/ws/rooms/{code}") as first:
                first.receive_json()
                self.assertEqual(client.get("/api/stats").json()["online_rooms"], 1)
                with client.websocket_connect(f"/ws/rooms/{code}") as second:
                    second.receive_json()
                    self.assertEqual(client.get("/api/stats").json()["online_rooms"], 1)
                self.assertEqual(client.get("/api/stats").json()["online_rooms"], 1)
            self.assertEqual(client.get("/api/stats").json()["online_rooms"], 0)
