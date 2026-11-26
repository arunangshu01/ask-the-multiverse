"""Ask the Multiverse API entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from anyio import to_thread
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__, settings, snapshot
from app.api import router
from app.settings import API_COMMON_PREFIX, CORS_ORIGINS, DATA_DIR
from app.store import DataUnavailable, Store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


log = logging.getLogger("app")


async def _refresh_loop(store: Store) -> None:
    """Pick up newly published snapshots without a redeploy."""
    while True:
        await asyncio.sleep(settings.SNAPSHOT_REFRESH_S)
        try:
            if await to_thread.run_sync(snapshot.sync, settings.SNAPSHOT_BUCKET, settings.SNAPSHOT_PREFIX, DATA_DIR):
                await to_thread.run_sync(store.load)
        except Exception as exc:  # keep serving the current snapshot
            log.warning("snapshot refresh failed: %s", exc)


def create_app(store: Store | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or Store(DATA_DIR)
        task = None
        if store is None and settings.SNAPSHOT_BUCKET:
            app.state.store.cleanup = True
            try:
                await to_thread.run_sync(snapshot.sync, settings.SNAPSHOT_BUCKET, settings.SNAPSHOT_PREFIX, DATA_DIR)
            except Exception as exc:
                log.error("could not download the snapshot: %s", exc)
            task = asyncio.create_task(_refresh_loop(app.state.store))
        if app.state.store.snapshot == {}:
            try:
                app.state.store.load()
            except DataUnavailable as exc:
                log.error("%s", exc)
        yield
        if task:
            task.cancel()

    app = FastAPI(
        title="Ask the Multiverse API",
        description="Unofficial, fan-made index of the Marvel multiverse built from the Marvel Database "
                    "(CC BY-SA 3.0) and Wikidata (CC0). Every record links to its source.",
        version=__version__,
        docs_url=f"{API_COMMON_PREFIX}/docs",
        redoc_url=f"{API_COMMON_PREFIX}/redoc",
        openapi_url=f"{API_COMMON_PREFIX}/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"], max_age=600)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith(API_COMMON_PREFIX) and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DataUnavailable)
    async def unavailable(_: Request, exc: DataUnavailable):
        return JSONResponse({"detail": "The multiverse index is not loaded yet."}, status_code=503)

    app.include_router(router, prefix=API_COMMON_PREFIX)
    return app


app = create_app()
