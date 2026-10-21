FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY backend ./backend
COPY simulator ./simulator
RUN pip install --no-cache-dir .
COPY data ./data
RUN mkdir -p /app/data/media
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000"]

