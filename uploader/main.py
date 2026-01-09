import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kina.uploader")


async def main() -> None:
    logger.info("started")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
