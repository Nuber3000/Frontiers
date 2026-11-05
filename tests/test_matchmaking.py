import unittest

from fastapi.testclient import TestClient

from frontiers.app import create_app
from frontiers.matchmaking import Matchmaking
from frontiers.rooms import RoomStore


class MatchmakingTests(unittest.TestCase):
    def test_http_search_matches_two_sessions_and_allows_another_search_after_arrival(self):
        rooms = RoomStore()
        app = create_app(rooms)
        with TestClient(app) as first:
            second = TestClient(app)
            outsider = TestClient(app)
            path = "/api/matchmaking"
            self.assertEqual(first.post(path, json={"name": "First"}).json(), {"status": "waiting"})
            self.assertEqual(first.post(path, json={"name": "First again"}).json(), {"status": "waiting"})
            self.assertEqual(len(rooms.rooms), 0)
            self.assertEqual(outsider.get(path).status_code, 403)

            matched = second.post(path, json={"name": "Second"}).json()
            self.assertEqual(matched["status"], "matched")
            room = matched["room"]
            self.assertEqual(room["me"], 1)
            self.assertEqual([seat["name"] for seat in room["seats"]], ["First", "Second"])
            self.assertIsNone(room["game"])
            status = first.get(path)
            self.assertEqual(status.headers["cache-control"], "no-store")
            self.assertEqual(status.json()["room"]["code"], room["code"])
            self.assertEqual(status.json()["room"]["me"], 0)
            self.assertEqual(first.post(path + "/cancel").json()["status"], "matched")
            self.assertEqual(len(rooms.rooms), 1)

            with first.websocket_connect(f"/ws/rooms/{room['code']}") as socket:
                self.assertEqual(socket.receive_json()["state"]["code"], room["code"])
                self.assertEqual(first.get(path).json(), {"status": "idle"})
                self.assertEqual(first.post(path, json={"name": "First"}).json(), {"status": "waiting"})

    def test_cancel_and_expiry_remove_waiters(self):
        rooms = RoomStore()
        queue = Matchmaking(rooms)
        queue.start("cancelled", "Cancelled")
        self.assertEqual(queue.cancel("cancelled"), {"status": "idle"})
        queue.start("expired", "Expired")
        queue.searches["expired"].expires_at = 0
        self.assertEqual(queue.start("waiting", "Waiting"), {"status": "waiting"})
        self.assertEqual(queue.status("expired"), {"status": "idle"})
        self.assertFalse(rooms.rooms)

    def test_waiting_players_pair_when_capacity_is_available(self):
        rooms = RoomStore(max_rooms=1)
        existing = rooms.create("existing", "Existing")
        queue = Matchmaking(rooms)
        for session in ("first", "second", "third"):
            self.assertEqual(queue.start(session, session), {"status": "waiting"})
        del rooms.rooms[existing.code]
        self.assertEqual(queue.status("third"), {"status": "waiting"})
        self.assertEqual(queue.status("first")["room"]["code"], queue.status("second")["room"]["code"])
        self.assertEqual(len(rooms.rooms), 1)

    def test_first_waiter_at_ownership_limit_can_be_a_guest(self):
        rooms = RoomStore()
        queue = Matchmaking(rooms)
        for session in ("first", "second"):
            for _ in range(8):
                rooms.create(session, session)
            self.assertEqual(queue.start(session, session), {"status": "waiting"})
        third = queue.start("third", "third")
        self.assertEqual([seat["name"] for seat in third["room"]["seats"]], ["third", "first"])
        self.assertEqual(queue.status("second"), {"status": "waiting"})
