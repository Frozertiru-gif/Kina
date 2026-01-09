import logging

from fastapi import APIRouter, FastAPI

from app.db.engine import init_db
from app.routes import (
    admin,
    ads,
    auth,
    catalog,
    favorites,
    health,
    internal,
    referral,
    subscriptions,
    titles,
    watch,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kina.api")


def create_app() -> FastAPI:
    app = FastAPI(title="Kina API")

    api_router = APIRouter(prefix="/api")
    api_router.include_router(health.router)
    api_router.include_router(auth.router)
    api_router.include_router(catalog.router)
    api_router.include_router(titles.router)
    api_router.include_router(favorites.router)
    api_router.include_router(watch.router)
    api_router.include_router(ads.router)
    api_router.include_router(subscriptions.router)
    api_router.include_router(referral.router)
    api_router.include_router(internal.router)
    api_router.include_router(admin.router)

    app.include_router(api_router)

    @app.on_event("startup")
    async def startup() -> None:
        await init_db()
        logger.info("started")

    return app


app = create_app()
