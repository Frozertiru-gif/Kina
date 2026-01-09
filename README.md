# Kina Mono-Repo

Production-ready mono-repo for API, Telegram bot, uploader service, and web/admin apps.

## Stack
- Python 3.11+, FastAPI, aiogram 3.x
- PostgreSQL, Redis
- React + Vite (WebApp and Admin)
- Docker, docker-compose, Nginx

## Services
- `api`: FastAPI backend with Alembic migrations
- `bot`: Telegram bot (aiogram 3.x)
- `uploader`: Uploads local files to Telegram storage chat to obtain `file_id`
- `webapp`: React client
- `admin`: React admin panel
- `infra`: Docker and Nginx configuration

## Quick Start (Docker)
1. Copy environment file and fill values:
   ```bash
   cp .env.example .env
   ```
2. Start services:
   ```bash
   docker compose -f infra/docker-compose.yml up --build
   ```
3. Run Alembic migrations:
   ```bash
   docker compose -f infra/docker-compose.yml exec api alembic upgrade head
   ```

## Environment Variables
See `.env.example` for required variables. No secrets are committed.

### Local Bot API Server
Large files (300–3000MB) require a local Bot API server. Configure:
- `TELEGRAM_API_BASE_URL` (example: `http://telegram-bot-api:8081`)
- `TELEGRAM_FILE_API_BASE_URL` (example: `http://telegram-bot-api:8081/file`)

## Notes
- Redis is used for rate limiting, queues (`send_video_queue`, `send_video_vip_queue`, `notify_queue`), and ad token TTL.
- Video delivery is strictly via Telegram `file_id` obtained by the uploader.
