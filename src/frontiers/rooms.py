"""Комнаты живут в памяти одного процесса; доступ к месту задаёт сессия браузера."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
import hmac
import secrets
import time

from frontiers.catalog import LEADERS, STARTER_DECK, validate_deck
from frontiers.engine import Game


class RoomError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Seat:
    session: str
    name: str
    leader: str = "sun"
    deck: list[str] = field(default_factory=lambda: list(STARTER_DECK))
    ready: bool = False


@dataclass
class Room:
    code: str
    seats: list[Seat]
    game: Game | None = None
    revision: int = 0
    touched: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    connections: dict = field(default_factory=lambda: {0: set(), 1: set()})
    action_times: dict = field(default_factory=lambda: {0: deque(), 1: deque()})

    def member(self, session: str) -> int:
        for index, seat in enumerate(self.seats):
            if hmac.compare_digest(seat.session, session):
                return index
        raise RoomError("Это место принадлежит другой сессии браузера. Войдите по приглашению.", 403)

    def changed(self) -> None:
        self.revision += 1
        self.touched = time.monotonic()

    def join(self, session: str, name: str) -> int:
        for index, seat in enumerate(self.seats):
            if hmac.compare_digest(seat.session, session):
                return index
        if len(self.seats) == 2:
            raise RoomError("В комнате уже два игрока.", 409)
        self.seats.append(Seat(session, name))
        self.changed()
        return 1

    def set_ready(self, side: int, leader: str, deck: list[str], ready: bool) -> None:
        if self.game and self.game.phase != "finished":
            raise RoomError("Во время матча нельзя менять колоду.", 409)
        validate_deck(deck, leader)
        seat = self.seats[side]
        seat.leader, seat.deck, seat.ready = leader, list(deck), ready
        if len(self.seats) == 2 and all(seat.ready for seat in self.seats):
            self.game = Game.create([seat.name for seat in self.seats],
                                    [seat.deck for seat in self.seats],
                                    [seat.leader for seat in self.seats])
            for seat in self.seats:
                seat.ready = False
        self.changed()

    def apply(self, side: int, action: dict, version: int) -> None:
        if not self.game:
            raise RoomError("Сначала оба игрока должны подтвердить готовность.", 409)
        now = time.monotonic()
        times = self.action_times[side]
        while times and times[0] < now - 10:
            times.popleft()
        if len(times) >= 180:
            raise RoomError("Слишком много команд. Подождите несколько секунд.", 429)
        times.append(now)
        self.game = self.game.act(side, action, version)
        self.changed()

    def view(self, side: int) -> dict:
        return {
            "code": self.code, "me": side, "revision": self.revision,
            "seats": [{"name": seat.name, "leader": seat.leader, "faction": LEADERS[seat.leader]["faction"], "ready": seat.ready,
                       "online": bool(self.connections[index])}
                      for index, seat in enumerate(self.seats)],
            "my_deck": list(self.seats[side].deck),
            "my_leader": self.seats[side].leader,
            "game": self.game.view(side) if self.game else None,
        }

    async def broadcast(self) -> None:
        async def send(side, socket):
            try:
                await asyncio.wait_for(socket.send_json({"type": "state", "state": self.view(side)}), 3)
            except Exception:
                self.connections[side].discard(socket)
                try:
                    await socket.close(code=1011)
                except Exception:
                    pass
        await asyncio.gather(*(send(side, socket) for side, sockets in self.connections.items()
                               for socket in tuple(sockets)))


class RoomStore:
    def __init__(self, max_rooms: int = 128, waiting_ttl: float = 3600,
                 match_ttl: float = 86400):
        self.rooms: dict[str, Room] = {}
        if max_rooms < 1 or waiting_ttl <= 0 or match_ttl <= 0:
            raise ValueError("Лимиты комнат и время хранения должны быть положительными.")
        self.max_rooms = max_rooms
        self.waiting_ttl = waiting_ttl
        self.match_ttl = match_ttl

    def create(self, session: str, name: str) -> Room:
        if len(self.rooms) >= self.max_rooms:
            raise RoomError("Сервер заполнен. Попробуйте создать комнату позже.", 503)
        owned = sum(room.seats[0].session == session for room in self.rooms.values())
        if owned >= 8:
            raise RoomError("Вы уже создали несколько комнат. Используйте существующее приглашение.", 429)
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            if code not in self.rooms:
                break
        room = Room(code, [Seat(session, name)])
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room:
        room = self.rooms.get(code.strip().upper())
        if room is None:
            raise RoomError("Комната не найдена или уже удалена. Создайте новое приглашение.", 404)
        return room

    async def cleanup(self) -> None:
        now = time.monotonic()
        for code, room in tuple(self.rooms.items()):
            async with room.lock:
                ttl = self.match_ttl if room.game and room.game.phase != "finished" else self.waiting_ttl
                if now - room.touched <= ttl:
                    continue
                self.rooms.pop(code, None)
                for sockets in room.connections.values():
                    for socket in tuple(sockets):
                        try:
                            await asyncio.wait_for(socket.close(code=1001), 1)
                        except Exception:
                            pass
