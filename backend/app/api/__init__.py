from fastapi import APIRouter

from app.api import ask, graph, meta, realities

router = APIRouter()
router.include_router(meta.router)
router.include_router(realities.router)
router.include_router(graph.router)
router.include_router(ask.router)
