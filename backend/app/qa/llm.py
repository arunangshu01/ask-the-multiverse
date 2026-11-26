"""Groq (primary) and Gemini (fallback) chat calls, temperature 0, JSON or text."""

from __future__ import annotations

import json
import logging

import httpx

from app import settings

log = logging.getLogger("app.qa.llm")


def configured() -> bool:
    return bool(settings.GROQ_API_KEY or settings.GEMINI_API_KEY)


async def _groq(system: str, user: str, as_json: bool, max_tokens: int) -> str | None:
    if not settings.GROQ_API_KEY:
        return None
    payload = {"model": settings.GROQ_MODEL, "temperature": 0, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if as_json:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_S) as client:
        resp = await client.post("https://api.groq.com/openai/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, json=payload)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            return None
        return (choice["message"].get("content") or "").strip()


async def _gemini(system: str, user: str, as_json: bool, max_tokens: int) -> str | None:
    if not settings.GEMINI_API_KEY:
        return None
    config = {"temperature": 0, "maxOutputTokens": max_tokens}
    if as_json:
        config["responseMimeType"] = "application/json"
    payload = {"system_instruction": {"parts": [{"text": system}]}, "contents": [{"parts": [{"text": user}]}],
               "generationConfig": config}
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_S) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": settings.GEMINI_API_KEY}, json=payload)
        resp.raise_for_status()
        cand = resp.json()["candidates"][0]
        if cand.get("finishReason") != "STOP":
            return None
        return "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought")).strip()


async def complete(system: str, user: str, as_json: bool = False, max_tokens: int = 700) -> tuple[str | None, str | None]:
    """(text, provider) from the first provider that answers, else (None, None)."""
    for name, fn in (("groq", _groq), ("gemini", _gemini)):
        try:
            text = await fn(system, user, as_json, max_tokens)
        except httpx.HTTPStatusError as exc:
            log.warning("%s failed: HTTP %s %s", name, exc.response.status_code, exc.response.text[:200])
            continue
        except Exception as exc:  # network errors, malformed responses
            log.warning("%s failed: %r", name, exc)
            continue
        if text:
            return text, name
    return None, None


def parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        out = json.loads(text[text.find("{"): text.rfind("}") + 1])
        return out if isinstance(out, dict) else None
    except ValueError:
        return None
