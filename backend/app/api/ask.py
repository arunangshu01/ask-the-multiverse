"""Multiverse Console: POST /ask streams progress, the query, the answer and citations (SSE)."""

from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import settings
from app.qa import engine, llm, tools
from app.ratelimit import RateLimiter

router = APIRouter()
visitor_limit = RateLimiter(settings.ASK_PER_VISITOR_PER_MIN, settings.ASK_PER_VISITOR_BURST)
global_limit = RateLimiter(settings.ASK_GLOBAL_PER_MIN, settings.ASK_GLOBAL_PER_MIN)
COOKIE = "__session"  # the only cookie Firebase Hosting forwards to Cloud Run

EXAMPLES = [
    "Who has fought both Thanos and Galactus?",
    "What is the origin of Spider-Man?",
    "Are Thor and Loki enemies?",
    "Which X-Men have also been Avengers?",
    "When did Spider-Man first fight Venom?",
    "Who killed Gwen Stacy?",
    "Who has Thanos fought in films?",
    "Show every variant of Wolverine",
    "When did Spider-Man first appear?",
    "How many realities exist?",
    "Tell me about Earth-92131",
    "Who are Thor's siblings?",
    "Who fought in the Infinity Gauntlet?",
]


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=400)


@router.get("/ask/meta")
def ask_meta():
    return {"llm": llm.configured(), "examples": EXAMPLES,
            "tools": {n: d for n, (_, _, d) in tools.TOOLS.items()}}


@router.post("/ask")
async def ask(body: AskBody, request: Request):
    visitor = request.cookies.get(COOKIE) or secrets.token_urlsafe(16)
    if not global_limit.allow("site"):
        raise HTTPException(429, "The console is busy right now. Please try again in a minute.")
    if not visitor_limit.allow(visitor):
        raise HTTPException(429, "You're asking faster than the console allows. Please wait a moment.")
    store = request.app.state.store

    async def stream():
        async for ev in engine.ask(store, body.question):
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    resp = StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    if COOKIE not in request.cookies:
        resp.set_cookie(COOKIE, visitor, max_age=86400 * 30, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")
    return resp
