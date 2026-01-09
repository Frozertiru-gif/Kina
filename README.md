# Kina

## API database setup

### Environment

Copy the example env file and set `DATABASE_URL`:

```bash
cp .env.example .env
```

Then edit `.env` to provide the correct `DATABASE_URL`.

### Run migrations (docker compose)

```bash
docker compose exec api alembic -c /api/alembic.ini upgrade head
```

### Seed data (docker compose)

```bash
docker compose exec api python /api/scripts/seed.py
```
