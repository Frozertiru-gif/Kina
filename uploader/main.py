import asyncio
import json
import logging
import mimetypes
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from sqlalchemy import (
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from logging_utils import configure_logging

from models import (
    Admin,
    AuditEvent,
    Episode,
    MediaVariant,
    Season,
    Subscription,
    Title,
    TitleType,
    UploadJob,
    User,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    log_level: str = "INFO"
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    bot_token: str
    storage_chat_id: int

    use_local_bot_api: bool = False
    local_bot_api_base_url: str = "http://local-bot-api:8081"
    telegram_api_base_url: str = "https://api.telegram.org"

    upload_ingest_dir: str = "/data/ingest"
    upload_archive_dir: str | None = None
    upload_failed_dir: str | None = None
    upload_poll_seconds: int = 3
    upload_max_retries: int = 3
    upload_backoff_seconds: int = 10
    upload_max_concurrent: int = 1
    upload_max_file_mb: int = 2000

@dataclass(frozen=True)
class ParsedVariant:
    kind: str
    title_id: int | None
    episode_id: int | None
    audio_id: int
    quality_id: int


MOVIE_PATTERN = re.compile(r"^title_(\d+)_{1,2}a_(\d+)_{1,2}q_(\d+)\.mp4$")
EPISODE_PATTERN = re.compile(r"^title_(\d+)_{1,2}e_(\d+)_{1,2}a_(\d+)_{1,2}q_(\d+)\.mp4$")
FILENAME_SUFFIX_PATTERN = re.compile(r"(?:\s*(?:—|-)?\s*копия|\s*\(1\))$", re.IGNORECASE)


logger = logging.getLogger("kina.uploader")


class UploadError(RuntimeError):
    def __init__(self, code: str, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def _classify_telegram_error(description: str) -> tuple[str, bool]:
    lowered = description.lower()
    if "file too large" in lowered or "file is too big" in lowered or "file_too_large" in lowered:
        return ("FILE_TOO_LARGE", False)
    if "chat not found" in lowered or "chat_not_found" in lowered:
        return ("CHAT_NOT_FOUND", False)
    if "bot was blocked" in lowered or "bot blocked" in lowered or "bot_blocked" in lowered:
        return ("BOT_BLOCKED", False)
    if "forbidden" in lowered:
        return ("FORBIDDEN", False)
    if "codec" in lowered or "unsupported" in lowered or "invalid" in lowered:
        return ("INVALID_CODEC", False)
    return ("TELEGRAM_ERROR", False)


async def _log_audit_event(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_type="service",
            actor_user_id=None,
            actor_admin_id=None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata,
        )
    )


async def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level.upper())

    ingest_dir = Path(settings.upload_ingest_dir)
    ingest_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = _prepare_optional_dir(settings.upload_archive_dir)
    failed_dir = _prepare_optional_dir(settings.upload_failed_dir)

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    base_url = _resolve_telegram_base_url(settings)
    logger.info(
        "uploader started",
        extra={
            "action": "startup",
            "request_id": "startup",
            "ingest_dir": str(ingest_dir),
            "archive_dir": str(archive_dir) if archive_dir else None,
            "failed_dir": str(failed_dir) if failed_dir else None,
            "max_concurrent": settings.upload_max_concurrent,
            "telegram_base_url": base_url,
            "use_local_bot_api": settings.use_local_bot_api,
            "storage_chat_id": settings.storage_chat_id,
        },
    )

    semaphore = asyncio.Semaphore(settings.upload_max_concurrent)
    workers = [
        asyncio.create_task(
            worker_loop(
                worker_id=i + 1,
                settings=settings,
                session_factory=session_factory,
                redis=redis,
                archive_dir=archive_dir,
                failed_dir=failed_dir,
                semaphore=semaphore,
            )
        )
        for i in range(settings.upload_max_concurrent)
    ]

    scan_task = asyncio.create_task(
        scan_loop(
            settings=settings,
            session_factory=session_factory,
            ingest_dir=ingest_dir,
            failed_dir=failed_dir,
            redis=redis,
        )
    )

    await asyncio.gather(*workers, scan_task)


async def scan_loop(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    ingest_dir: Path,
    failed_dir: Path | None,
    redis: Redis,
) -> None:
    while True:
        await scan_ingest(
            settings=settings,
            session_factory=session_factory,
            ingest_dir=ingest_dir,
            failed_dir=failed_dir,
        )
        if await drain_control_queue(redis):
            await scan_ingest(
                settings=settings,
                session_factory=session_factory,
                ingest_dir=ingest_dir,
                failed_dir=failed_dir,
            )
        await asyncio.sleep(settings.upload_poll_seconds)


async def drain_control_queue(redis: Redis) -> bool:
    rescan_requested = False
    while True:
        payload = await redis.lpop("uploader_control_queue")
        if payload is None:
            break
        try:
            message = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "invalid control payload",
                extra={
                    "action": "control_payload_invalid",
                    "request_id": "control",
                    "payload": payload,
                },
            )
            continue
        if message.get("action") == "rescan":
            logger.info(
                "rescan requested",
                extra={"action": "control_rescan", "request_id": "control"},
            )
            rescan_requested = True
    return rescan_requested

async def scan_ingest(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    ingest_dir: Path,
    failed_dir: Path | None,
) -> None:
    max_bytes = settings.upload_max_file_mb * 1024 * 1024
    total_files = 0
    matched_files = 0
    not_ready_files = 0
    queued_jobs = 0
    for file_path in sorted(ingest_dir.iterdir()):
        if not file_path.is_file():
            continue
        total_files += 1
        can_read, exc_type = can_read_file(file_path)
        if not can_read:
            logger.info(
                "file locked, skipping ingest",
                extra={
                    "action": "ingest_skip_locked",
                    "request_id": "scan_ingest",
                    "ingest_filename": file_path.name,
                    "exc_type": exc_type,
                },
            )
            continue
        if not await is_file_ready(file_path):
            not_ready_files += 1
            logger.info(
                "file not ready yet",
                extra={
                    "action": "ingest_file_not_ready",
                    "request_id": "scan_ingest",
                    "ingest_filename": file_path.name,
                },
            )
            continue
        resolved = str(file_path.resolve())
        async with session_factory() as session:
            existing = await session.execute(
                select(UploadJob).where(
                    UploadJob.local_path == resolved,
                    UploadJob.status != "ready",
                )
            )
            if existing.scalar_one_or_none():
                continue

        size_bytes = file_path.stat().st_size
        if size_bytes > max_bytes:
            await move_to_failed(
                file_path,
                failed_dir,
                reason=f"file_too_large:{size_bytes}",
            )
            continue

        parsed = parse_variant_filename(file_path.name)
        if parsed is None:
            logger.warning(
                "invalid ingest filename",
                extra={
                    "action": "invalid_ingest_filename",
                    "request_id": "scan_ingest",
                    "ingest_filename": file_path.name,
                    "reason": "bad_filename",
                    "expected_format": (
                        "title_{id}__a_{audio_id}__q_{quality_id}.mp4 or "
                        "title_{id}_a_{audio_id}_q_{quality_id}.mp4 or "
                        "title_{id}__e_{episode_id}__a_{audio_id}__q_{quality_id}.mp4 or "
                        "title_{id}_e_{episode_id}_a_{audio_id}_q_{quality_id}.mp4"
                    ),
                },
            )
            await move_to_failed(file_path, failed_dir, reason="bad_filename")
            continue
        matched_files += 1

        async with session_factory() as session:
            variant = await find_variant(session, parsed)
            if variant is None:
                logger.warning(
                    "variant not found",
                    extra={
                        "action": "variant_not_found",
                        "request_id": "scan_ingest",
                        "title_id": parsed.title_id,
                        "episode_id": parsed.episode_id,
                        "audio_id": parsed.audio_id,
                        "quality_id": parsed.quality_id,
                        "ingest_filename": file_path.name,
                    },
                )
                await move_to_failed(file_path, failed_dir, reason="variant_not_found")
                continue

            job = UploadJob(
                local_path=resolved,
                variant_id=variant.id,
                status="queued",
                attempts=0,
                last_error=None,
            )
            session.add(job)
            await session.commit()
            queued_jobs += 1
            logger.info(
                "job queued",
                extra={
                    "job_id": job.id,
                    "variant_id": variant.id,
                    "file_path": file_path.name,
                },
            )
    logger.info(
        "ingest scan complete",
        extra={
            "action": "ingest_scan_complete",
            "request_id": "scan_ingest",
            "total_files": total_files,
            "matched_files": matched_files,
            "not_ready_files": not_ready_files,
            "queued_jobs": queued_jobs,
        },
    )


async def worker_loop(
    *,
    worker_id: int,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    archive_dir: Path | None,
    failed_dir: Path | None,
    semaphore: asyncio.Semaphore,
) -> None:
    while True:
        async with semaphore:
            job = await claim_job(session_factory)
            if job is None:
                await asyncio.sleep(settings.upload_poll_seconds)
                continue
            try:
                await handle_job(
                    job=job,
                    settings=settings,
                    session_factory=session_factory,
                    redis=redis,
                    archive_dir=archive_dir,
                    failed_dir=failed_dir,
                )
            except Exception as exc:
                logger.exception(
                    "job failed",
                    extra={
                        "action": "upload_job_failed",
                        "request_id": f"job:{job.id}",
                        "job_id": job.id,
                        "variant_id": job.variant_id,
                        "file_path": job.local_path,
                        "error": str(exc),
                        "attempts": job.attempts,
                        "worker_id": worker_id,
                    },
                )


async def claim_job(session_factory: async_sessionmaker[AsyncSession]) -> UploadJob | None:
    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(UploadJob)
                .where(UploadJob.status == "queued")
                .with_for_update(skip_locked=True)
                .order_by(UploadJob.id)
            )
            job = result.scalars().first()
            if job is None:
                return None
            previous_status = job.status
            job.status = "uploading"
            job.attempts += 1
            await _log_audit_event(
                session,
                action="upload_job_status_changed",
                entity_type="upload_job",
                entity_id=job.id,
                metadata={
                    "from": previous_status,
                    "to": job.status,
                    "variant_id": job.variant_id,
                },
            )
        await session.commit()
        await session.refresh(job)
        return job


async def handle_job(
    *,
    job: UploadJob,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    archive_dir: Path | None,
    failed_dir: Path | None,
) -> None:
    file_path = Path(job.local_path)
    if not file_path.exists():
        await mark_job_failed(
            session_factory,
            job,
            error="file_missing",
            variant_status="failed",
        )
        logger.warning(
            "file missing",
            extra={
                "action": "upload_job_file_missing",
                "request_id": f"job:{job.id}",
                "job_id": job.id,
                "file_path": job.local_path,
            },
        )
        return

    async with session_factory() as session:
        variant = await session.get(MediaVariant, job.variant_id)
        if variant is None:
            await mark_job_failed(
                session_factory,
                job,
                error="variant_missing",
                variant_status="failed",
            )
            await move_to_failed(file_path, failed_dir, reason="variant_missing")
            return
        variant.status = "uploading"
        await session.commit()

    try:
        size_bytes = file_path.stat().st_size
        logger.info(
            "upload start",
            extra={
                "action": "upload_start",
                "request_id": f"job:{job.id}",
                "job_id": job.id,
                "variant_id": job.variant_id,
                "filepath": str(file_path),
                "filesize": size_bytes,
                "storage_chat_id": settings.storage_chat_id,
            },
        )
        message_id, file_id = await send_video(
            settings=settings,
            variant_id=job.variant_id,
            file_path=file_path,
        )
    except UploadError as exc:
        logger.error(
            "upload error",
            exc_info=True,
            extra={
                "action": "upload_error",
                "request_id": f"job:{job.id}",
                "job_id": job.id,
                "variant_id": job.variant_id,
            },
        )
        logger.warning(
            "upload error",
            extra={
                "action": "upload_job_error",
                "request_id": f"job:{job.id}",
                "job_id": job.id,
                "variant_id": job.variant_id,
                "file_path": file_path.name,
                "error_code": exc.code,
                "retryable": exc.retryable,
            },
        )
        await handle_upload_error(
            settings=settings,
            session_factory=session_factory,
            job=job,
            variant_id=job.variant_id,
            file_path=file_path,
            failed_dir=failed_dir,
            error=exc.code,
            retryable=exc.retryable,
        )
        return
    except Exception as exc:
        logger.error(
            "upload error",
            exc_info=True,
            extra={
                "action": "upload_error",
                "request_id": f"job:{job.id}",
                "job_id": job.id,
                "variant_id": job.variant_id,
            },
        )
        await handle_upload_error(
            settings=settings,
            session_factory=session_factory,
            job=job,
            variant_id=job.variant_id,
            file_path=file_path,
            failed_dir=failed_dir,
            error=str(exc),
            retryable=False,
        )
        return

    async with session_factory() as session:
        variant = await session.get(MediaVariant, job.variant_id)
        if variant is None:
            await mark_job_failed(
                session_factory,
                job,
                error="variant_missing_after_upload",
                variant_status="failed",
            )
            await move_to_failed(file_path, failed_dir, reason="variant_missing")
            return
        variant.telegram_file_id = file_id
        variant.status = "ready"
        variant.storage_chat_id = settings.storage_chat_id
        variant.storage_message_id = message_id
        variant.size_bytes = size_bytes
        variant.error = None

        job.status = "ready"
        job.last_error = None
        await _log_audit_event(
            session,
            action="upload_job_status_changed",
            entity_type="upload_job",
            entity_id=job.id,
            metadata={
                "from": "uploading",
                "to": "ready",
                "variant_id": job.variant_id,
            },
        )
        await session.commit()

        await notify_subscribers_if_needed(
            session=session,
            redis=redis,
            variant=variant,
        )

    await finalize_file(file_path, archive_dir)

    logger.info(
        "upload success",
        extra={
            "action": "upload_success",
            "request_id": f"job:{job.id}",
            "job_id": job.id,
            "variant_id": job.variant_id,
            "file_path": file_path.name,
            "message_id": message_id,
            "telegram_file_id": file_id,
        },
    )


async def handle_upload_error(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    job: UploadJob,
    variant_id: int,
    file_path: Path,
    failed_dir: Path | None,
    error: str,
    retryable: bool,
) -> None:
    attempts = job.attempts
    if not retryable or attempts >= settings.upload_max_retries:
        await mark_job_failed(
            session_factory,
            job,
            error=error,
            variant_status="failed",
        )
        await move_to_failed(file_path, failed_dir, reason=error)
        return

    await mark_job_error(session_factory, job, error)
    backoff = settings.upload_backoff_seconds * attempts
    logger.warning(
        "upload error, retrying",
        extra={
            "action": "upload_job_retry",
            "request_id": f"job:{job.id}",
            "job_id": job.id,
            "variant_id": variant_id,
            "file_path": file_path.name,
            "attempts": attempts,
            "backoff": backoff,
            "error": error,
            "retryable": True,
        },
    )
    await asyncio.sleep(backoff)
    async with session_factory() as session:
        job_db = await session.get(UploadJob, job.id)
        if job_db:
            job_db.status = "queued"
            await session.commit()


async def mark_job_error(
    session_factory: async_sessionmaker[AsyncSession],
    job: UploadJob,
    error: str,
) -> None:
    async with session_factory() as session:
        job_db = await session.get(UploadJob, job.id)
        if not job_db:
            return
        job_db.last_error = error
        await session.commit()


async def mark_job_failed(
    session_factory: async_sessionmaker[AsyncSession],
    job: UploadJob,
    error: str,
    variant_status: str,
) -> None:
    async with session_factory() as session:
        job_db = await session.get(UploadJob, job.id)
        if not job_db:
            return
        job_db.status = "failed"
        job_db.last_error = error
        variant = await session.get(MediaVariant, job.variant_id)
        if variant:
            variant.status = variant_status
            variant.error = error
        await _log_audit_event(
            session,
            action="upload_job_status_changed",
            entity_type="upload_job",
            entity_id=job.id,
            metadata={
                "from": "uploading",
                "to": "failed",
                "variant_id": job.variant_id,
                "error": error,
            },
        )
        await session.commit()


async def send_video(
    *,
    settings: Settings,
    variant_id: int,
    file_path: Path,
) -> tuple[int, str]:
    base_url = _resolve_telegram_base_url(settings)
    url = f"{base_url}/bot{settings.bot_token}/sendVideo"

    mime_type, _ = mimetypes.guess_type(file_path.name)
    mime_type = mime_type or "application/octet-stream"

    data = {
        "chat_id": str(settings.storage_chat_id),
        "caption": f"variant:{variant_id}",
        "supports_streaming": "true",
        "disable_notification": "true",
    }

    timeout = httpx.Timeout(60.0, read=600.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            with file_path.open("rb") as file_handle:
                files = {"video": (file_path.name, file_handle, mime_type)}
                response = await client.post(url, data=data, files=files)
    except httpx.TimeoutException as exc:
        raise UploadError("timeout", True) from exc
    except httpx.RequestError as exc:
        raise UploadError("connection_error", True) from exc

    if response.status_code == 429:
        raise UploadError("HTTP_429", True)
    if 500 <= response.status_code <= 599:
        raise UploadError(f"HTTP_{response.status_code}", True)
    if response.status_code == 403:
        raise UploadError("FORBIDDEN", False)
    if response.status_code != 200:
        raise UploadError(f"HTTP_{response.status_code}", False)
    try:
        payload = response.json()
    except ValueError as exc:
        raise UploadError("invalid_response", False) from exc
    if not payload.get("ok"):
        description = payload.get("description") or payload.get("error_description") or str(payload)
        code, retryable = _classify_telegram_error(description)
        raise UploadError(code, retryable)
    result = payload.get("result") or {}
    message_id = result.get("message_id")
    video = result.get("video") or {}
    file_id = video.get("file_id")
    if not message_id or not file_id:
        raise RuntimeError("telegram_missing_fields")
    return int(message_id), str(file_id)


async def notify_subscribers_if_needed(
    *,
    session: AsyncSession,
    redis: Redis,
    variant: MediaVariant,
) -> None:
    if variant.episode_id is None:
        return
    episode_result = await session.execute(
        select(Episode, Season, Title)
        .join(Season, Episode.season_id == Season.id)
        .join(Title, Episode.title_id == Title.id)
        .where(Episode.id == variant.episode_id)
    )
    row = episode_result.first()
    if not row:
        return
    episode, season, title = row
    if not episode.published_at:
        return
    if title.type != TitleType.SERIES:
        return
    result = await session.execute(
        select(User.tg_user_id)
        .join(Subscription, Subscription.user_id == User.id)
        .where(
            Subscription.title_id == title.id,
            Subscription.enabled.is_(True),
        )
    )
    tg_user_ids = [row[0] for row in result.fetchall()]
    if not tg_user_ids:
        return

    text = (
        "Новая серия вышла: "
        f"{title.name} — S{season.season_number}E{episode.episode_number}. Открыть?"
    )
    enqueued = 0
    deduped = 0
    for tg_user_id in tg_user_ids:
        dedupe_key = f"notif:{tg_user_id}:{episode.id}"
        dedupe_set = await redis.set(dedupe_key, "1", nx=True, ex=60 * 60 * 24 * 7)
        if not dedupe_set:
            deduped += 1
            continue
        payload = {
            "tg_user_id": tg_user_id,
            "title_id": title.id,
            "episode_id": episode.id,
            "text": text,
            "variant_id": variant.id,
        }
        await redis.rpush("notify_queue", json.dumps(payload, ensure_ascii=False))
        enqueued += 1

    await _log_audit_event(
        session,
        action="notification_enqueued",
        entity_type="episode",
        entity_id=episode.id,
        metadata={
            "title_id": title.id,
            "variant_id": variant.id,
            "total_subscribers": len(tg_user_ids),
            "enqueued": enqueued,
            "deduped": deduped,
        },
    )
    await session.commit()


def parse_variant_filename(filename: str) -> ParsedVariant | None:
    normalized = normalize_variant_filename(filename)
    movie_match = MOVIE_PATTERN.match(normalized)
    if movie_match:
        title_id, audio_id, quality_id = map(int, movie_match.groups())
        return ParsedVariant(
            kind="movie",
            title_id=title_id,
            episode_id=None,
            audio_id=audio_id,
            quality_id=quality_id,
        )

    episode_match = EPISODE_PATTERN.match(normalized)
    if episode_match:
        title_id, episode_id, audio_id, quality_id = map(int, episode_match.groups())
        return ParsedVariant(
            kind="episode",
            title_id=title_id,
            episode_id=episode_id,
            audio_id=audio_id,
            quality_id=quality_id,
        )

    return None


def normalize_variant_filename(filename: str) -> str:
    path = Path(filename)
    stem = path.stem
    while True:
        cleaned = FILENAME_SUFFIX_PATTERN.sub("", stem)
        if cleaned == stem:
            break
        stem = cleaned
    return f"{stem}{path.suffix}"


async def find_variant(session: AsyncSession, parsed: ParsedVariant) -> MediaVariant | None:
    query = select(MediaVariant).where(
        MediaVariant.audio_id == parsed.audio_id,
        MediaVariant.quality_id == parsed.quality_id,
    )
    if parsed.kind == "movie":
        query = query.where(
            MediaVariant.title_id == parsed.title_id,
            MediaVariant.episode_id.is_(None),
        )
    else:
        query = query.where(
            MediaVariant.title_id == parsed.title_id,
            MediaVariant.episode_id == parsed.episode_id,
        )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def finalize_file(file_path: Path, archive_dir: Path | None) -> None:
    can_read, _ = can_read_file(file_path)
    if not can_read:
        logger.info(
            "move deferred, file locked",
            extra={
                "action": "move_deferred_locked",
                "ingest_filename": file_path.name,
            },
        )
        return
    if archive_dir:
        destination = unique_destination(archive_dir, file_path.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        move_file(file_path, destination, action="archive_file")
    else:
        file_path.unlink(missing_ok=True)


async def move_to_failed(file_path: Path, failed_dir: Path | None, reason: str) -> None:
    logger.warning(
        "move to failed",
        extra={"ingest_filename": file_path.name, "reason": reason},
    )
    if not failed_dir:
        return
    if not file_path.exists():
        return
    can_read, _ = can_read_file(file_path)
    if not can_read:
        logger.info(
            "move deferred, file locked",
            extra={
                "action": "move_deferred_locked",
                "ingest_filename": file_path.name,
            },
        )
        return
    destination = unique_destination(failed_dir, file_path.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    move_file(file_path, destination, action="move_to_failed", reason=reason)


def move_file(
    source: Path,
    destination: Path,
    *,
    action: str,
    reason: str | None = None,
) -> None:
    backoff_seconds = [0.5, 1, 2, 4, 8]
    for attempt in range(len(backoff_seconds) + 1):
        try:
            shutil.move(str(source), str(destination))
            return
        except PermissionError as exc:
            if attempt >= len(backoff_seconds):
                logger.info(
                    "move deferred, file locked",
                    extra={
                        "action": "move_deferred_locked",
                        "ingest_filename": source.name,
                        "destination": str(destination),
                        "reason": reason,
                        "attempts": attempt + 1,
                    },
                )
                return
            time.sleep(backoff_seconds[attempt])
        except FileNotFoundError as exc:
            if attempt >= len(backoff_seconds):
                logger.warning(
                    "file missing during move",
                    extra={
                        "action": action,
                        "ingest_filename": source.name,
                        "destination": str(destination),
                        "reason": reason,
                        "error": str(exc),
                        "attempts": attempt + 1,
                    },
                )
                return
            time.sleep(backoff_seconds[attempt])
        except OSError as exc:
            logger.exception(
                "failed to move file",
                extra={
                    "action": action,
                    "ingest_filename": source.name,
                    "destination": str(destination),
                    "reason": reason,
                    "error": str(exc),
                },
            )
            return


def unique_destination(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return directory / f"{stem}_{timestamp}{suffix}"


def _prepare_optional_dir(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_telegram_base_url(settings: Settings) -> str:
    if settings.use_local_bot_api and settings.local_bot_api_base_url:
        return settings.local_bot_api_base_url.rstrip("/")
    return settings.telegram_api_base_url.rstrip("/")


async def is_file_ready(file_path: Path) -> bool:
    try:
        stat_before = file_path.stat()
    except OSError:
        return False
    if not file_path.exists():
        return False
    await asyncio.sleep(1)
    try:
        stat_after = file_path.stat()
    except OSError:
        return False
    return stat_before.st_size == stat_after.st_size


def can_read_file(file_path: Path) -> tuple[bool, str | None]:
    try:
        with file_path.open("rb") as handle:
            handle.read(8192)
    except (PermissionError, OSError) as exc:
        return False, exc.__class__.__name__
    return True, None


if __name__ == "__main__":
    asyncio.run(main())
