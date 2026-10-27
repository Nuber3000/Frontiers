"""Локальный запуск: python -m frontiers."""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Сервер Frontiers")
    parser.add_argument("--host", default=os.getenv("FRONTIERS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FRONTIERS_PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="Перезапускать сервер при изменении кода")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Порт должен быть от 1 до 65535.")
    uvicorn.run("frontiers.app:app", host=args.host, port=args.port,
                reload=args.reload, ws_max_size=16384)


if __name__ == "__main__":
    main()
