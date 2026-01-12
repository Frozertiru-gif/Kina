# Kina Mono-Repo

Продакшен-готовый монорепозиторий для API, Telegram-бота, сервиса загрузчика и веб/админ приложений.

## Стек
- Python 3.11+, FastAPI, aiogram 3.x
- PostgreSQL, Redis
- React + Vite (WebApp и Admin)
- Docker, docker-compose, Nginx

## Быстрый старт (Docker)
1. Скопируйте файл окружения и заполните значения:
   ```bash
   cp .env.example .env
   ```
   Убедитесь, что `DATABASE_URL` задан (обязательно).
2. Запустите сервисы:
   ```bash
   docker compose up --build
   ```
3. Примените миграции:
   ```bash
   docker compose exec api alembic -c /api/alembic.ini upgrade head
   ```
4. Заполните базовые данные:
   ```bash
   docker compose exec api python /api/scripts/seed.py
   ```

## Локальные адреса
- http://localhost/ (webapp)
- http://localhost/admin/ (admin)
- http://localhost/api/health (api)

## Admin UI + API
- Открыть админку: http://localhost/admin/
- База Admin API: http://localhost/api/admin

Сборка статических файлов админки для Nginx:
```bash
cd admin
npm install
npm run build
```

## WebApp (Telegram) build
Продакшен-бандл генерируется в `webapp/dist` из `webapp/src`.

```bash
cd webapp
npm install
npm run build
```

После сборки разверните содержимое `webapp/dist` (Nginx уже раздает его в
`webapp/Dockerfile`).

### Авторизация админки
Задайте следующие переменные окружения:
- `ADMIN_SERVICE_TOKEN` (токен для `X-Admin-Token`, при отсутствии берется `SERVICE_TOKEN`)
- `ADMIN_ALLOWLIST` (опциональный CSV со списком Telegram user ID, которым разрешен доступ)

Если `ADMIN_ALLOWLIST` задан, добавьте заголовок `X-Admin-User-Id` со значением из allowlist.

### Примеры curl для Admin API
```bash
curl -X GET http://localhost/api/admin/titles?limit=5 \
  -H "X-Admin-Token: $ADMIN_SERVICE_TOKEN"

curl -X POST http://localhost/api/admin/titles \
  -H "X-Admin-Token: $ADMIN_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"movie","name":"Demo Movie","year":2024}'

curl -X POST http://localhost/api/admin/variants \
  -H "X-Admin-Token: $ADMIN_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title_id":1,"audio_id":1,"quality_id":1,"status":"pending"}'
```

## Telegram Bot
Бот читает очереди Redis и отправляет карточки/видео пользователям. В чате он не ищет тайтлы.

### Обязательные переменные окружения
- `BOT_TOKEN`
- `REDIS_URL`
- `DATABASE_URL`
- `SERVICE_TOKEN`
- `ADMIN_TOKEN` (если нужны админские команды бота)
- `API_BASE_URL` (рекомендуемое значение для docker-compose: `http://api:8000`)
- `INGEST_CHAT_ID` (чат для приема ingest-сообщений)
- `STORAGE_CHAT_ID` (ID чата хранилища в Telegram, если используется)

### QA
- Для админских запросов используйте заголовок `X-Admin-Token`.

### Запуск бота (Docker)
```bash
docker compose up --build bot
```

### Очереди Redis
- `send_watch_card_queue` → `{tg_user_id, variant_id, title_id, episode_id, mode}`
- `send_video_queue` → `{tg_user_id, variant_id}`
- `send_video_vip_queue` → `{tg_user_id, variant_id}`
- `notify_queue` → `{tg_user_id, title_id, episode_id, text, variant_id}`

### Подписки и уведомления
- Подписка на сериалы:
  - WebApp: нажмите кнопку 🔔 на странице тайтла.
  - Bot: нажмите 🔔 на карточке.
- Уведомления отправляются, когда вариант эпизода становится `ready` **и** у эпизода есть
  `published_at`. Это позволяет заранее загружать серии перед публикацией.
- Ключ дедупликации (Redis): `notif:{tg_user_id}:{episode_id}` (TTL 7 дней).

## API v1 (DEV auth bypass)
Установите `ENVIRONMENT=local` и `DEV_AUTH_BYPASS=true` (плюс `DEV_TG_USER_ID` или заголовок).

### Эндпоинты
- GET  /api/health
- POST /api/auth/webapp
- GET  /api/catalog/top
- GET  /api/catalog/search
- GET  /api/title/{title_id}
- GET  /api/title/{title_id}/episodes
- GET  /api/favorites
- POST /api/favorites/toggle
- GET  /api/subscriptions
- POST /api/subscriptions/toggle
- POST /api/watch/request
- POST /api/watch/resolve
- POST /api/watch/dispatch
- POST /api/ads/start
- POST /api/ads/complete
- GET  /api/ads/status
- POST /api/referral/apply
- POST /api/internal/bot/send_watch_card
- POST /api/internal/bot/send_video
- POST /api/internal/bot/send_notification
- POST /api/internal/user/subscription_toggle
- GET  /api/internal/metrics

### Авторизация (DEV bypass)
```bash
curl -X POST http://localhost/api/auth/webapp \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Id: 123456' \
  -d '{"initData": ""}'
```

### Watch request (success)
```bash
curl -X POST http://localhost/api/watch/request \
  -H 'Content-Type: application/json' \
  -H 'X-Init-Data: <telegram_init_data>' \
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'
```

### Watch resolve (best variant)
```bash
curl -X POST http://localhost/api/watch/resolve \
  -H 'Content-Type: application/json' \
  -H 'X-Init-Data: <telegram_init_data>' \
  -d '{"title_id":1,"episode_id":null,"audio_id":null,"quality_id":null}'
```

### Watch request (variant not found)
```bash
curl -X POST http://localhost/api/watch/request \
  -H 'Content-Type: application/json' \
  -H 'X-Init-Data: <telegram_init_data>' \
  -d '{"title_id":1,"episode_id":null,"audio_id":99,"quality_id":99}'
```

### Watch request (too many requests)
```bash
curl -X POST http://localhost/api/watch/request \
  -H 'Content-Type: application/json' \
  -H 'X-Init-Data: <telegram_init_data>' \
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'
```

### Ads flow (DEV bypass)
```bash
curl -X POST http://localhost/api/watch/request \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Id: 123456' \
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'

curl -X POST http://localhost/api/ads/start \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Id: 123456' \
  -d '{"variant_id":1}'

curl -X POST http://localhost/api/ads/complete \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Id: 123456' \
  -d '{"nonce":"<nonce_from_ads_start>"}'

curl -X POST http://localhost/api/watch/request \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Id: 123456' \
  -d '{"title_id":1,"episode_id":null,"audio_id":1,"quality_id":1}'

curl -X POST http://localhost/api/watch/dispatch \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-User-Id: 123456' \
  -d '{"variant_id":1}'
```

## Лимиты (API)
| Область | Эндпоинт | Лимит |
| --- | --- | --- |
| Пользователь | `GET /api/catalog/search` | 10 запросов / 10 секунд |
| Пользователь | `POST /api/watch/request` | 20 запросов / 60 секунд (плюс 2с debounce) |
| Пользователь | `POST /api/ads/start` | 5 запросов / 60 секунд |
| Пользователь | `POST /api/ads/complete` | 10 запросов / 60 секунд |
| Пользователь | `POST /api/referral/apply` | 2 запроса / 24 часа на каждого приглашенного |
| Реферер | `POST /api/referral/apply` | 10 запросов / 24 часа на каждого реферера |
| Админ токен | `/api/admin/*` | 60 запросов / 60 секунд |
| Сервисный токен | `/api/internal/*` | 120 запросов / 60 секунд |

## Предпочтения просмотра и значения по умолчанию
- Хранятся в `user_state`: `preferred_audio_id`, `preferred_quality_id`, `last_title_id`, `last_episode_id`.
- `/api/watch/resolve` подставляет отсутствующие audio/quality из сохраненных предпочтений.
- Если по-прежнему нет значений, выбираются детерминированные дефолты:
  - Audio: минимальный `audio_id` среди активных дорожек для тайтла/эпизода.
  - Quality: максимальный `height` среди активных качеств для тайтла/эпизода.

## Навигация по эпизодам в боте
- Prev/next выбирает соседний эпизод по `episode_number` в пределах сезона.
- На границе сезона переходит между сезонами (последний эпизод предыдущего сезона или первый следующего).

## Модерация пользователей админом
Бан/разбан пользователей:
```bash
curl -X POST http://localhost/api/admin/users/123/ban \
  -H "X-Admin-Token: $ADMIN_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"abuse"}'

curl -X POST http://localhost/api/admin/users/123/unban \
  -H "X-Admin-Token: $ADMIN_SERVICE_TOKEN"
```

## Внутренние метрики
```bash
curl -X GET http://localhost/api/internal/metrics \
  -H "X-Service-Token: $SERVICE_TOKEN"
```

## WebApp dev
```bash
cd webapp
npm install
npm run dev
```

### WebApp prod
```bash
docker compose up --build
```

## Примечания
- Контейнер Nginx отдает заглушки HTML для `/` и `/admin/`.
- Бот при старте падает, если `BOT_TOKEN` не задан.

### Local Bot API
Задайте `USE_LOCAL_BOT_API=true` и `LOCAL_BOT_API_BASE_URL=http://local-bot-api:8081`, чтобы
отправлять загрузки в локальный Bot API вместо `https://api.telegram.org`.
