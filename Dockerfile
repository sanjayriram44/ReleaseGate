FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    DB_PATH=/data/releasegate.db PORT=8080

WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app

# Non-root user; /data is the persistent volume mount point for the SQLite file.
RUN useradd --system --uid 10001 app && mkdir /data && chown app /data
USER app
VOLUME /data

EXPOSE 8080
CMD ["sh", "-c", "exec /srv/.venv/bin/uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT}"]
