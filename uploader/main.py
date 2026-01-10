import asyncio
import json
import logging
import mimetypes
import enum
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    log_level: str = "INFO"
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    bot_token: str
    storage_chat_id: int

    use_local_bot_api: bool = True
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


class Base(DeclarativeBase):
    pass


class MediaVariant(Base):
    __tablename__ = "media_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_id: Mapped[int] = mapped_column(Integer)
    episode_id: Mapped[int | None] = mapped_column(Integer)
    audio_id: Mapped[int] = mapped_column(Integer)
    quality_id: Mapped[int] = mapped_column(Integer)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    storage_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    storage_message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))


class TitleType(enum.Enum):
    MOVIE = "movie"
    SERIES = "series"


class Title(Base):
    __tablename__ = "titles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[TitleType] = mapped_column(Enum(TitleType, name="title_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_id: Mapped[int] = mapped_column(Integer)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_id: Mapped[int] = mapped_column(Integer)
    season_id: Mapped[int] = mapped_column(Integer)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_path: Mapped[str] = mapped_column(String(512))
    variant_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50))
    attempts: Mapped[int] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id"))
    action: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(255))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


@dataclass(frozen=True)
class ParsedVariant:
    kind: str
    title_id: int | None
    episode_id: int | None
    audio_id: int
    quality_id: int


MOVIE_PATTERN = re.compile(r"^title_(\d+)__a_(\d+)__q_(\d+)\.[^.]+$")
EPISODE_PATTERN = re.compile(r"^ep_(\d+)__a_(\d+)__q_(\d+)\.[^.]+$")


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

    logger.info(
        "uploader started",
        extra={
            "action": "startup",
            "request_id": "startup",
            "ingest_dir": str(ingest_dir),
            "archive_dir": str(archive_dir) if archive_dir else None,
            "failed_dir": str(failed_dir) if failed_dir else None,
            "max_concurrent": settings.upload_max_concurrent,
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
    for file_path in sorted(ingest_dir.iterdir()):
        if not file_path.is_file():
            continue
        resolved = str(file_path.resolve())
        async with session_factory() as session:
            existing = await session.execute(
                select(UploadJob).where(
                    UploadJob.local_path == resolved,
                    UploadJob.status != "done",
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
            await move_to_failed(file_path, failed_dir, reason="invalid_filename")
            continue

        async with session_factory() as session:
            variant = await find_variant(session, parsed)
            if variant is None:
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
            logger.info(
                "job queued",
                extra={
                    "job_id": job.id,
                    "variant_id": variant.id,
                    "filename": file_path.name,
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
                        "filename": job.local_path,
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
                "filename": job.local_path,
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
        message_id, file_id = await send_video(
            settings=settings,
            variant_id=job.variant_id,
            file_path=file_path,
        )
    except UploadError as exc:
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

    size_bytes = file_path.stat().st_size
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
        variant.storage_chat_id = settings.storage_chat_id
        variant.storage_message_id = message_id
        variant.status = "ready"
        variant.size_bytes = size_bytes
        variant.error = None

        job.status = "done"
        job.last_error = None
        await _log_audit_event(
            session,
            action="upload_job_status_changed",
            entity_type="upload_job",
            entity_id=job.id,
            metadata={
                "from": "uploading",
                "to": "done",
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
            "action": "upload_job_done",
            "request_id": f"job:{job.id}",
            "job_id": job.id,
            "variant_id": job.variant_id,
            "filename": file_path.name,
            "message_id": message_id,
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
            "filename": file_path.name,
            "attempts": attempts,
            "backoff": backoff,
            "error": error,
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
    if settings.use_local_bot_api:
        base_url = settings.local_bot_api_base_url.rstrip("/")
    else:
        base_url = settings.telegram_api_base_url.rstrip("/")
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
    movie_match = MOVIE_PATTERN.match(filename)
    if movie_match:
        title_id, audio_id, quality_id = map(int, movie_match.groups())
        return ParsedVariant(
            kind="movie",
            title_id=title_id,
            episode_id=None,
            audio_id=audio_id,
            quality_id=quality_id,
        )

    episode_match = EPISODE_PATTERN.match(filename)
    if episode_match:
        episode_id, audio_id, quality_id = map(int, episode_match.groups())
        return ParsedVariant(
            kind="episode",
            title_id=None,
            episode_id=episode_id,
            audio_id=audio_id,
            quality_id=quality_id,
        )

    return None


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
        query = query.where(MediaVariant.episode_id == parsed.episode_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def finalize_file(file_path: Path, archive_dir: Path | None) -> None:
    if archive_dir:
        destination = unique_destination(archive_dir, file_path.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_path.rename(destination)
    else:
        file_path.unlink(missing_ok=True)


async def move_to_failed(file_path: Path, failed_dir: Path | None, reason: str) -> None:
    logger.warning(
        "move to failed",
        extra={"filename": file_path.name, "reason": reason},
    )
    if not failed_dir:
        return
    destination = unique_destination(failed_dir, file_path.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_path.rename(destination)


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


if __name__ == "__main__":
    asyncio.run(main())
from logging_utils import configure_logging
