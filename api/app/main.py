import logging
import os
import uuid

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.dependencies import BannedUserError
from app.logging_utils import configure_logging

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

configure_logging(service="api")
logger = logging.getLogger("kina.api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kina API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        tg_user_id = getattr(request.state, "tg_user_id", None)
        if (
            os.getenv("AUTH_UNAUTHORIZED_DEBUG", "0") == "1"
            and response.status_code == 401
            and request.url.path.startswith("/api")
        ):
            logger.info(
                "unauthorized request",
                extra={
                    "action": "unauthorized_debug",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "has_x_init_data": "x-init-data" in request.headers,
                    "has_authorization": "authorization" in request.headers,
                    "has_cookie": "cookie" in request.headers,
                },
            )
        logger.info(
            "request completed",
            extra={
                "action": "request",
                "request_id": request_id,
                "tg_user_id": tg_user_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response

    @app.exception_handler(BannedUserError)
    async def banned_user_handler(_: Request, __: BannedUserError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": "banned"})

    api_router = APIRouter(prefix="/api")

    @api_router.get("")
    async def api_root() -> dict[str, object]:
        return {"ok": True, "docs": "/api/docs"}
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
