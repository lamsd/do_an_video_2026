FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.3
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY app ./app
COPY README.md ./

EXPOSE 8088
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]

