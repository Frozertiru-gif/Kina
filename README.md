# Kina Mono-Repo

Production-grade mono-repo skeleton for API, Telegram bot, uploader service, and web/admin apps.

## Stack
- Python 3.11+, FastAPI, aiogram 3.x
- PostgreSQL, Redis
- React + Vite (WebApp and Admin)
- Docker, docker-compose, Nginx

## Quick Start (Docker)
1. Copy environment file and fill values:
   ```bash
   cp .env.example .env
   ```
   Ensure `DATABASE_URL` is set (required).
2. Start services:
   ```bash
   docker compose up --build
   ```
3. Apply migrations:
   ```bash
   docker compose exec api alembic -c /api/alembic.ini upgrade head
   ```
4. Seed initial data:
   ```bash
   docker compose exec api python /api/scripts/seed.py
   ```

## Local URLs
- http://localhost/ (webapp)
- http://localhost/admin/ (admin)
- http://localhost/api/health (api)

## API v1 (DEV auth bypass)
Set `ENVIRONMENT=local` and `DEV_AUTH_BYPASS=true` (plus `DEV_TG_USER_ID` or header).

### Endpoints
- GET  /api/health
- POST /api/auth/webapp
- GET  /api/catalog/top
- GET  /api/catalog/search
- GET  /api/title/{title_id}
- GET  /api/title/{title_id}/episodes
- GET  /api/favorites
- POST /api/favorites/toggle
- POST /api/watch/request
- POST /api/internal/bot/send_watch_card
- POST /api/internal/bot/send_video
- POST /api/internal/bot/send_notification

### Auth (DEV bypass)
```bash
curl -X POST http://localhost/api/auth/webapp \\
  -H 'Content-Type: application/json' \\
  -H 'X-Dev-User-Id: 123456' \\
  -d '{"initData": ""}'
```

### Watch request (success)
```bash
curl -X POST http://localhost/api/watch/request \\
  -H 'Content-Type: application/json' \\
  -H 'X-Init-Data: <telegram_init_data>' \\
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'
```

### Watch request (variant not found)
```bash
curl -X POST http://localhost/api/watch/request \\
  -H 'Content-Type: application/json' \\
  -H 'X-Init-Data: <telegram_init_data>' \\
  -d '{"title_id":1,"episode_id":null,"audio_id":99,"quality_id":99}'
```

### Watch request (too many requests)
```bash
curl -X POST http://localhost/api/watch/request \\
  -H 'Content-Type: application/json' \\
  -H 'X-Init-Data: <telegram_init_data>' \\
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'
```

## Notes
- The Nginx container serves placeholder HTML pages for `/` and `/admin/`.
- Bot startup fails fast when `BOT_TOKEN`/`TELEGRAM_BOT_TOKEN` is missing.
