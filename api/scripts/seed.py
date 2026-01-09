import asyncio

from app.db.session import AsyncSessionLocal
from app.models.admin import Admin
from app.models.content import Episode, Season, Title
from app.models.media import AudioTrack, MediaVariant, Quality


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        movie = Title(type="movie", name="Seed Movie", description="Seeded movie")
        series = Title(type="series", name="Seed Series", description="Seeded series")
        session.add_all([movie, series])
        await session.flush()

        season = Season(title_id=series.id, season_number=1)
        session.add(season)
        await session.flush()

        episode_one = Episode(
            season_id=season.id,
            episode_number=1,
            name="Episode 1",
        )
        episode_two = Episode(
            season_id=season.id,
            episode_number=2,
            name="Episode 2",
        )
        session.add_all([episode_one, episode_two])
        await session.flush()

        audio_ru = AudioTrack(language="ru", name="Russian")
        audio_en = AudioTrack(language="en", name="English")
        quality_hd = Quality(label="HD", resolution="1280x720")
        quality_full = Quality(label="FullHD", resolution="1920x1080")
        session.add_all([audio_ru, audio_en, quality_hd, quality_full])
        await session.flush()

        variants = [
            MediaVariant(
                title_id=movie.id,
                audio_id=audio_ru.id,
                quality_id=quality_hd.id,
                status="pending",
            ),
            MediaVariant(
                title_id=movie.id,
                audio_id=audio_en.id,
                quality_id=quality_full.id,
                status="pending",
            ),
            MediaVariant(
                title_id=series.id,
                episode_id=episode_one.id,
                audio_id=audio_ru.id,
                quality_id=quality_hd.id,
                status="pending",
            ),
            MediaVariant(
                title_id=series.id,
                episode_id=episode_two.id,
                audio_id=audio_en.id,
                quality_id=quality_full.id,
                status="pending",
            ),
        ]
        session.add_all(variants)

        admin = Admin(email="admin@kina.local")
        session.add(admin)

        await session.commit()

        print("movie_id:", movie.id)
        print("series_id:", series.id)
        print("season_id:", season.id)
        print("episode_ids:", episode_one.id, episode_two.id)
        print("audio_ids:", audio_ru.id, audio_en.id)
        print("quality_ids:", quality_hd.id, quality_full.id)
        print("media_variant_ids:", [variant.id for variant in variants])
        print("admin_id:", admin.id)


if __name__ == "__main__":
    asyncio.run(seed())
