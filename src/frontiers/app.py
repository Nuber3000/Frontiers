"""HTTP и WebSocket API. Каждая команда обрабатывается под блокировкой комнаты."""

import asyncio
from collections import deque
from contextlib import asynccontextmanager, suppress
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from frontiers.catalog import STARTER_DECK, catalog_view
from frontiers.engine import RuleError, StaleState
from frontiers.rooms import RoomError, RoomStore


COOKIE = "frontiers_session"
STATIC = Path(__file__).with_name("static")
logger = logging.getLogger("frontiers")


class NameBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Игрок", min_length=1, max_length=32)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Введите имя без управляющих символов.")
        return value


class ReadyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    leader: str = Field(default="sun", max_length=32)
    deck: list[str] = Field(default_factory=lambda: list(STARTER_DECK), min_length=22, max_length=60)
    ready: bool = True


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["mulligan", "play", "choose", "leader", "pass", "concede"]
    version: int = Field(ge=0, strict=True)
    card_id: str | None = Field(default=None, max_length=64)
    row: Literal["melee", "ranged", "siege"] | None = None
    target_id: str | None = Field(default=None, max_length=64)
    card_ids: list[str] = Field(default_factory=list, max_length=2)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def same_origin(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True  # Небраузерные клиенты не обязаны передавать Origin.
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host


def create_app(store: RoomStore | None = None, secure_cookies: bool | None = None) -> FastAPI:
    room_store = store if store is not None else RoomStore(
        max_rooms=int(os.getenv("FRONTIERS_MAX_ROOMS", "128")))
    cookie_secure = (os.getenv("FRONTIERS_SECURE_COOKIES", "0").lower() in {"1", "true", "yes"}
                     if secure_cookies is None else secure_cookies)

    @asynccontextmanager
    async def lifespan(application):
        async def clean_rooms():
            while True:
                await asyncio.sleep(60)
                await room_store.cleanup()
        task = asyncio.create_task(clean_rooms())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Frontiers", version="0.1.0", lifespan=lifespan)
    app.state.rooms = room_store

    @app.middleware("http")
    async def request_policy(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(
                request.headers.get("origin"), request.headers.get("host")):
            return JSONResponse({"detail": "Запрос с другого сайта запрещён."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'")
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/rooms") else "no-cache"
        return response

    @app.exception_handler(RoomError)
    async def room_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(StaleState)
    async def stale_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(RuleError)
    async def rule_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    def session(request, response: Response | None = None) -> str:
        token = request.cookies.get(COOKIE, "")
        if not 32 <= len(token) <= 128:
            if response is None:
                raise RoomError("Сессия не найдена. Откройте приглашение и войдите в комнату.", 403)
            token = secrets.token_urlsafe(32)
        if response is not None:
            response.set_cookie(COOKIE, token, httponly=True, secure=cookie_secure,
                                samesite="strict", max_age=604800, path="/")
        return digest(token)

    def membership(request, code):
        room = room_store.get(code)
        return room, room.member(session(request))

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/catalog")
    async def catalog():
        return catalog_view()

    @app.post("/api/rooms", status_code=201)
    async def create_room(body: NameBody, request: Request, response: Response):
        room = room_store.create(session(request, response), body.name)
        return room.view(0)

    @app.post("/api/rooms/{code}/join")
    async def join_room(code: str, body: NameBody, request: Request, response: Response):
        room = room_store.get(code)
        async with room.lock:
            side = room.join(session(request, response), body.name)
            await room.broadcast()
            return room.view(side)

    @app.get("/api/rooms/{code}")
    async def room_state(code: str, request: Request):
        room, side = membership(request, code)
        return room.view(side)

    @app.post("/api/rooms/{code}/ready")
    async def ready(code: str, body: ReadyBody, request: Request):
        room, side = membership(request, code)
        async with room.lock:
            try:
                room.set_ready(side, body.leader, body.deck, body.ready)
            except ValueError as error:
                if isinstance(error, RoomError):
                    raise
                raise RoomError(str(error)) from None
            await room.broadcast()
            return room.view(side)

    @app.post("/api/rooms/{code}/actions")
    async def action(code: str, body: ActionBody, request: Request):
        room, side = membership(request, code)
        async with room.lock:
            room.apply(side, body.model_dump(exclude={"version"}, exclude_none=True), body.version)
            await room.broadcast()
            return room.view(side)

    @app.websocket("/ws/rooms/{code}")
    async def websocket_room(socket: WebSocket, code: str):
        if not same_origin(socket.headers.get("origin"), socket.headers.get("host")):
            await socket.close(code=1008)
            return
        try:
            room, side = membership(socket, code)
        except RoomError:
            await socket.close(code=1008)
            return
        async with room.lock:
            if len(room.connections[side]) >= 3:
                await socket.close(code=1008)
                return
            await socket.accept()
            room.connections[side].add(socket)
            await room.broadcast()
        times = deque()
        try:
            while True:
                message = await socket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                now = time.monotonic()
                while times and times[0] < now - 10:
                    times.popleft()
                times.append(now)
                text = message.get("text")
                if len(times) > 180 or not isinstance(text, str) or len(text) > 16384:
                    await socket.close(code=1008)
                    break
                try:
                    data = json.loads(text)
                    if data == {"type": "ping"}:
                        room.touched = now
                        await socket.send_json({"type": "pong"})
                        continue
                    body = ActionBody.model_validate(data)
                    async with room.lock:
                        room.apply(side, body.model_dump(exclude={"version"}, exclude_none=True), body.version)
                        await room.broadcast()
                except (json.JSONDecodeError, ValidationError):
                    await socket.send_json({"type": "error", "message": "Неверный формат команды."})
                except (RuleError, RoomError) as error:
                    await socket.send_json({"type": "error", "message": str(error), "state": room.view(side)})
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Ошибка соединения комнаты %s", code)
        finally:
            async with room.lock:
                room.connections[side].discard(socket)
                await room.broadcast()

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
    return app


app = create_app()
