from fastapi import FastAPI

from app.redis import close_redis
from app.routers import health, videos

app = FastAPI(title="Kina API")
app.include_router(health.router)
app.include_router(videos.router, prefix="/api")


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_redis()
