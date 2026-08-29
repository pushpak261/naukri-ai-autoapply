"""
AI Service HTTP surface.

Exposes the AI capabilities (previously imported directly inside the agent)
as REST endpoints so other services and the dashboard can call them over the
network. Also hosts the match-cache management endpoints (moved here from the
monolithic ``data.py`` because the cache is an AI artifact).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query

from api.deps import state

router = APIRouter(tags=["ai"])


# ---------------------------------------------------------------------------
# LLM completion (the canonical AI capability)
# ---------------------------------------------------------------------------
@router.post("/api/ai/complete")
async def ai_complete(payload: dict) -> dict:
    """Run a prompt through the configured LLM provider and return the text.

    Body: {prompt, temperature?, max_output_tokens?, response_mime_type?}
    """
    prompt = payload.get("prompt")
    if not prompt:
        return {"ok": False, "error": "prompt is required"}
    temperature = float(payload.get("temperature", 0.3))
    max_output_tokens = int(payload.get("max_output_tokens", 2048))
    response_mime_type = payload.get("response_mime_type", "text/plain")

    if not state.settings.ai.use_gemini or not state.settings.ai.gemini_api_key:
        return {"ok": False, "error": "Gemini is not configured on the AI service"}

    from src.naukri_agent.ai.llm_provider import GeminiProvider

    provider = GeminiProvider(
        api_key=state.settings.ai.gemini_api_key,
        model_name=state.settings.ai.model,
    )
    text = await provider.generate_content(
        prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
    )
    return {"ok": True, "text": text}


# ---------------------------------------------------------------------------
# Match cache management (moved from data.py)
# ---------------------------------------------------------------------------
@router.get("/api/cache/match-cache")
async def get_match_cache(search: str = Query("", max_length=200)) -> dict:
    cache_path = state.settings.project_root / "data" / "match_cache.json"
    if not cache_path.exists():
        return {"items": [], "total": 0}
    try:
        cache: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8"))
        items = []
        for key, value in cache.items():
            if search and search.lower() not in key.lower():
                continue
            parts = key.split("_", 1)
            items.append(
                {
                    "key": key,
                    "resume_hash": parts[0] if len(parts) > 0 else "",
                    "job_id": parts[1] if len(parts) > 1 else "",
                    "score": value.get("score", 0),
                    "should_apply": value.get("should_apply", False),
                    "matching_skills": value.get("matching_skills", []),
                    "missing_skills": value.get("missing_skills", []),
                    "reasoning": value.get("reasoning", ""),
                }
            )
        return {"items": items, "total": len(items)}
    except Exception:
        return {"items": [], "total": 0}


@router.get("/api/cache/match-cache/stats")
async def get_match_cache_stats() -> dict:
    cache_path = state.settings.project_root / "data" / "match_cache.json"
    if not cache_path.exists():
        return {"total_entries": 0, "avg_score": 0, "would_apply": 0, "would_skip": 0}
    try:
        cache: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8"))
        scores = [v.get("score", 0) for v in cache.values()]
        would_apply = sum(1 for v in cache.values() if v.get("should_apply", False))
        return {
            "total_entries": len(cache),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "would_apply": would_apply,
            "would_skip": len(cache) - would_apply,
        }
    except Exception:
        return {"total_entries": 0, "avg_score": 0, "would_apply": 0, "would_skip": 0}


@router.delete("/api/cache/match-cache")
async def clear_match_cache() -> dict:
    cache_path = state.settings.project_root / "data" / "match_cache.json"
    if cache_path.exists():
        cache_path.write_text("{}", encoding="utf-8")
    return {"status": "cleared", "message": "Match cache cleared"}
