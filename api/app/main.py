import logging

from fastapi import FastAPI

from app.db.engine import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kina.api")

app = FastAPI(title="Kina API")


@app.on_event("startup")
async def startup() -> None:
    await init_db()
    logger.info("started")


@app.get("/api/health")
async def health() -> dict[str, bool]:
    return {"ok": True}
