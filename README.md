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
2. Start services:
   ```bash
   docker compose up --build
   ```

## Local URLs
- http://localhost/ (webapp)
- http://localhost/admin/ (admin)
- http://localhost/api/health (api)

## Notes
- The Nginx container serves placeholder HTML pages for `/` and `/admin/`.
- Bot startup fails fast when `BOT_TOKEN`/`TELEGRAM_BOT_TOKEN` is missing.
