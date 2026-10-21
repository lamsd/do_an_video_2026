# Database migrations

Docker backend runs `alembic upgrade head` before Uvicorn. For local development:

```bash
alembic upgrade head
```

The FastAPI lifespan retains `Base.metadata.create_all()` only for the SQLite simulator/test path. Do not rely on it for PostgreSQL production evolution; create and review a new Alembic revision for each schema change.
