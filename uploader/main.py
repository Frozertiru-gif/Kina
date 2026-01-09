import asyncio
import logging


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("started")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
