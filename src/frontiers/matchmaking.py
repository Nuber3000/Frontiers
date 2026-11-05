"""FIFO matchmaking for the same server process that owns the rooms."""

from dataclasses import dataclass
import time

from frontiers.rooms import Room, RoomError, RoomStore


@dataclass
class Search:
    name: str
    expires_at: float
    room: Room | None = None


class Matchmaking:
    WAITING_TTL = 20
    MATCHED_TTL = 60
    MAX_SEARCHES = 256

    def __init__(self, rooms: RoomStore):
        self.rooms = rooms
        self.searches: dict[str, Search] = {}

    def cleanup(self) -> None:
        now = time.monotonic()
        for session, search in tuple(self.searches.items()):
            if search.expires_at <= now or (
                search.room is not None and self.rooms.rooms.get(search.room.code) is not search.room
            ):
                del self.searches[session]

    def start(self, session: str, name: str) -> dict:
        self.cleanup()
        if session not in self.searches:
            if len(self.searches) >= self.MAX_SEARCHES:
                raise RoomError("Очередь поиска заполнена. Попробуйте позже.", 503)
            self.searches[session] = Search(name, time.monotonic() + self.WAITING_TTL)
        return self.status(session)

    def status(self, session: str) -> dict:
        self.cleanup()
        search = self.searches.get(session)
        if search and search.room is None:
            search.expires_at = time.monotonic() + self.WAITING_TTL
            self._pair()
        return self._result(session)

    def cancel(self, session: str) -> dict:
        self.cleanup()
        search = self.searches.get(session)
        if search and search.room is None:
            del self.searches[session]
        return self._result(session)

    def arrived(self, session: str, room: Room) -> None:
        search = self.searches.get(session)
        if search and search.room is room:
            del self.searches[session]

    def _result(self, session: str) -> dict:
        search = self.searches.get(session)
        if search is None:
            return {"status": "idle"}
        if search.room is None:
            return {"status": "waiting"}
        return {"status": "matched", "room": search.room.view(search.room.member(session))}

    def _pair(self) -> None:
        waiting = [(session, search) for session, search in self.searches.items() if search.room is None]
        while len(waiting) >= 2 and len(self.rooms.rooms) < self.rooms.max_rooms:
            # A player at the room ownership limit can still take the guest seat.
            host_index = next((index for index, (session, _) in enumerate(waiting)
                               if self.rooms.can_host(session)), None)
            if host_index is None:
                return
            host, first = waiting.pop(host_index)
            guest, second = waiting.pop(0)
            room = self.rooms.create(host, first.name)
            room.join(guest, second.name)
            first.room = second.room = room
            first.expires_at = second.expires_at = time.monotonic() + self.MATCHED_TTL
