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

## Telegram Bot
The bot reads Redis queues and sends cards/videos to users. It does not search titles in chat.

### Required ENV
- `BOT_TOKEN`
- `REDIS_URL`
- `DATABASE_URL`
- `SERVICE_TOKEN`
- `API_BASE_URL`

### Run bot (Docker)
```bash
docker compose up --build bot
```

### Redis queues
- `send_watch_card_queue` → `{tg_user_id, variant_id, title_id, episode_id, mode}`
- `send_video_queue` → `{tg_user_id, variant_id}`
- `send_video_vip_queue` → `{tg_user_id, variant_id}`
- `notify_queue` → `{tg_user_id, title_id, episode_id, text}`

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
- POST /api/ads/start
- POST /api/ads/complete
- GET  /api/ads/status
- POST /api/internal/bot/send_watch_card
- POST /api/internal/bot/send_video
- POST /api/internal/bot/send_notification
- POST /api/internal/uploader/retry_job
- GET  /api/internal/uploader/jobs
- POST /api/internal/uploader/rescan

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

### Ads flow (DEV bypass)
```bash
curl -X POST http://localhost/api/watch/request \\
  -H 'Content-Type: application/json' \\
  -H 'X-Dev-User-Id: 123456' \\
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'

curl -X POST http://localhost/api/ads/start \\
  -H 'Content-Type: application/json' \\
  -H 'X-Dev-User-Id: 123456' \\
  -d '{"variant_id":1}'

curl -X POST http://localhost/api/ads/complete \\
  -H 'Content-Type: application/json' \\
  -H 'X-Dev-User-Id: 123456' \\
  -d '{"nonce":"<nonce_from_ads_start>"}'

curl -X POST http://localhost/api/watch/request \\
  -H 'Content-Type: application/json' \\
  -H 'X-Dev-User-Id: 123456' \\
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'
```

## Notes
- The Nginx container serves placeholder HTML pages for `/` and `/admin/`.
- Bot startup fails fast when `BOT_TOKEN` is missing.

## Uploader Service
Uploader watches the ingest folder, matches files to media variants, uploads them to Telegram
storage chat, and writes `file_id` + message details into the DB.

### Required ENV
- `STORAGE_CHAT_ID` (Telegram storage chat ID)
- `BOT_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`
- `UPLOAD_INGEST_DIR`

### Optional ENV
- `UPLOAD_ARCHIVE_DIR` (archive uploaded files)
- `UPLOAD_FAILED_DIR` (move invalid/failed files)
- `UPLOAD_POLL_SECONDS`
- `UPLOAD_MAX_RETRIES`
- `UPLOAD_BACKOFF_SECONDS`
- `UPLOAD_MAX_CONCURRENT`
- `UPLOAD_MAX_FILE_MB`
- `USE_LOCAL_BOT_API` (default `true`)
- `LOCAL_BOT_API_BASE_URL`
- `TELEGRAM_API_BASE_URL`

### Upload flow
1. Place file in ingest directory (default `./data/ingest`).
2. Uploader parses the filename and matches `media_variants`.
3. Uploader sends video to storage chat via `sendVideo`.
4. DB is updated with `telegram_file_id`, `storage_message_id`, `storage_chat_id`, and status.

### Naming convention
- Movie: `title_<title_id>__a_<audio_id>__q_<quality_id>.mp4`
- Episode: `ep_<episode_id>__a_<audio_id>__q_<quality_id>.mkv`

Examples:
- `title_12__a_1__q_2.mp4`
- `ep_345__a_1__q_2.mkv`

### Check uploader jobs
```bash
curl -H \"Authorization: Bearer $SERVICE_TOKEN\" \\
  \"http://localhost/api/internal/uploader/jobs?status=failed&limit=50\"
```

### Trigger rescan
```bash
curl -X POST -H \"Authorization: Bearer $SERVICE_TOKEN\" \\
  http://localhost/api/internal/uploader/rescan
```

### Local Bot API
Set `USE_LOCAL_BOT_API=true` and `LOCAL_BOT_API_BASE_URL=http://local-bot-api:8081` to send
uploads to a local Bot API instance instead of `https://api.telegram.org`.
