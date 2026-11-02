"""Room retention across disconnects, reconnects, and capacity cleanup."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from frontiers.rooms import RoomStore


class RoomCleanupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = Mock(return_value=1000)
        self.enterContext(patch("frontiers.rooms.time", SimpleNamespace(monotonic=self.clock)))
        self.store = RoomStore(max_rooms=1, disconnected_ttl=120)
        self.room = self.store.create("owner", "Alice")
        self.room.touched = 1000

    async def test_unvisited_invitation_expires_and_frees_capacity(self):
        self.clock.return_value = 1120
        self.assertEqual(await self.store.cleanup(), 0)
        self.clock.return_value = 1121
        self.assertEqual(await self.store.cleanup(), 1)
        self.assertEqual(await self.store.cleanup(), 0)
        replacement = self.store.create("other", "Bob")
        self.assertIn(replacement.code, self.store.rooms)

    async def test_last_disconnect_starts_full_grace_for_every_phase(self):
        for phase in (None, "mulligan", "playing", "finished"):
            with self.subTest(phase=phase):
                self.store.rooms[self.room.code] = self.room
                self.room.game = SimpleNamespace(phase=phase) if phase else None
                first, second = object(), object()
                self.clock.return_value = 1000
                self.room.connect(0, first)
                self.room.connect(1, second)
                self.clock.return_value = 2000
                self.room.disconnect(0, first)
                self.assertIsNone(self.room.disconnected_at)
                self.assertEqual(await self.store.cleanup(), 0)
                self.room.disconnect(1, second)
                self.clock.return_value = 2119
                self.assertEqual(await self.store.cleanup(), 0)
                self.clock.return_value = 2121
                self.assertEqual(await self.store.cleanup(), 1)

    async def test_reconnect_preserves_room_then_restarts_grace(self):
        socket = object()
        self.room.connect(0, socket)
        self.room.disconnect(0, socket)
        self.clock.return_value = 1110
        replacement = object()
        self.room.connect(0, replacement)
        self.clock.return_value = 5000
        self.assertEqual(await self.store.cleanup(), 0)
        self.room.disconnect(0, replacement)
        self.clock.return_value = 5119
        self.assertEqual(await self.store.cleanup(), 0)
        self.clock.return_value = 5121
        self.assertEqual(await self.store.cleanup(), 1)

    async def test_multiple_tabs_and_duplicate_disconnect_do_not_reset_grace(self):
        first, second = object(), object()
        self.room.connect(0, first)
        self.room.connect(0, second)
        self.room.disconnect(0, first)
        self.assertIsNone(self.room.disconnected_at)
        self.clock.return_value = 1010
        self.room.disconnect(0, second)
        self.clock.return_value = 1120
        self.room.disconnect(0, second)
        self.assertEqual(self.room.disconnected_at, 1010)
        self.clock.return_value = 1131
        self.assertEqual(await self.store.cleanup(), 1)

    async def test_failed_broadcast_starts_grace(self):
        # Mock objects are hashable and model a failed transport.
        socket = Mock(send_json=AsyncMock(side_effect=OSError("Disconnected")), close=AsyncMock())
        self.room.connect(0, socket)
        self.clock.return_value = 2000
        await self.room.broadcast()
        self.assertFalse(self.room.online)
        self.assertEqual(self.room.disconnected_at, 2000)
        self.room.disconnect(0, socket)  # The endpoint's finally block runs later.
        self.clock.return_value = 2121
        self.assertEqual(await self.store.cleanup(), 1)

    async def test_cleanup_skips_busy_room_without_delaying_other_rooms(self):
        self.store.max_rooms = 2
        other = self.store.create("other", "Bob")
        other.touched = 1000
        self.clock.return_value = 2000
        async with self.room.lock:
            self.assertEqual(await self.store.cleanup(), 1)
            self.assertIn(self.room.code, self.store.rooms)
        self.assertEqual(await self.store.cleanup(), 1)


if __name__ == "__main__":
    unittest.main()
