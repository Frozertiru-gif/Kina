import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Admin,
    AudioTrack,
    Episode,
    MediaVariant,
    Quality,
    Season,
    Title,
)
from app.models.models import TitleType


async def seed() -> None:
    async with SessionLocal() as session:
        existing_admin = await session.execute(select(Admin).limit(1))
        if existing_admin.scalar() is not None:
            raise RuntimeError("Seed already applied; admins table is not empty.")

        movie = Title(
            type=TitleType.MOVIE,
            name="Kina Movie",
            original_name="Kina Movie",
            description="Seed movie",
            year=2024,
            poster_url=None,
            is_published=True,
        )
        series = Title(
            type=TitleType.SERIES,
            name="Kina Series",
            original_name="Kina Series",
            description="Seed series",
            year=2024,
            poster_url=None,
            is_published=True,
        )
        session.add_all([movie, series])
        await session.flush()

        season = Season(title_id=series.id, season_number=1, name="Season 1")
        session.add(season)
        await session.flush()

        now = datetime.now(timezone.utc)
        episode_one = Episode(
            title_id=series.id,
            season_id=season.id,
            episode_number=1,
            name="Episode 1",
            description="Seed episode 1",
            published_at=now,
        )
        episode_two = Episode(
            title_id=series.id,
            season_id=season.id,
            episode_number=2,
            name="Episode 2",
            description="Seed episode 2",
            published_at=now,
        )
        session.add_all([episode_one, episode_two])
        await session.flush()

        audio_ru = AudioTrack(name="Russian", code="ru", is_active=True)
        audio_en = AudioTrack(name="English", code="en", is_active=True)
        quality_720 = Quality(name="720p", height=720, is_active=True)
        quality_1080 = Quality(name="1080p", height=1080, is_active=True)
        session.add_all([audio_ru, audio_en, quality_720, quality_1080])
        await session.flush()

        movie_variant_one = MediaVariant(
            title_id=movie.id,
            episode_id=None,
            audio_id=audio_ru.id,
            quality_id=quality_720.id,
            status="pending",
        )
        movie_variant_two = MediaVariant(
            title_id=movie.id,
            episode_id=None,
            audio_id=audio_en.id,
            quality_id=quality_1080.id,
            status="pending",
        )
        episode_variant_one = MediaVariant(
            title_id=series.id,
            episode_id=episode_one.id,
            audio_id=audio_ru.id,
            quality_id=quality_720.id,
            status="pending",
        )
        episode_variant_two = MediaVariant(
            title_id=series.id,
            episode_id=episode_two.id,
            audio_id=audio_en.id,
            quality_id=quality_1080.id,
            status="pending",
        )
        session.add_all(
            [movie_variant_one, movie_variant_two, episode_variant_one, episode_variant_two]
        )
        await session.flush()

        admin = Admin(tg_user_id=0, role="owner", is_active=True)
        session.add(admin)
        await session.flush()

        await session.commit()

        print(
            "movie_id={movie_id} series_id={series_id} season_id={season_id} "
            "episode_ids=[{episode_one_id},{episode_two_id}] audio_ids=[{audio_ru_id},{audio_en_id}] "
            "quality_ids=[{quality_720_id},{quality_1080_id}] variant_ids=[{movie_v1},{movie_v2},{ep_v1},{ep_v2}] "
            "admin_id={admin_id}".format(
                movie_id=movie.id,
                series_id=series.id,
                season_id=season.id,
                episode_one_id=episode_one.id,
                episode_two_id=episode_two.id,
                audio_ru_id=audio_ru.id,
                audio_en_id=audio_en.id,
                quality_720_id=quality_720.id,
                quality_1080_id=quality_1080.id,
                movie_v1=movie_variant_one.id,
                movie_v2=movie_variant_two.id,
                ep_v1=episode_variant_one.id,
                ep_v2=episode_variant_two.id,
                admin_id=admin.id,
            )
        )


if __name__ == "__main__":
    asyncio.run(seed())
