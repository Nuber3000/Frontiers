FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version README.md ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable --no-cache

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "frontiers", "--host", "0.0.0.0", "--port", "8000"]