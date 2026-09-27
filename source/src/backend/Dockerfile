FROM ghcr.io/astral-sh/uv:0.12.3 AS uv
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app
RUN useradd --system --create-home --uid 10001 appuser \
    && true
COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8088
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
