"""Run management and SSE event routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from backend.dependencies import get_repository, get_run_manager
from backend.schemas.run import RunCreate, RunStatus, RunSummary
from backend.services.run_manager import RunManager
from src.naukri_agent.database.repository import SQLAlchemyRepository, parse_search_keywords

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunStatus)
async def start_run(
    body: RunCreate,
    manager: RunManager = Depends(get_run_manager),
) -> RunStatus:
    try:
        return await manager.start(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/current", response_model=RunStatus)
async def current_run(
    manager: RunManager = Depends(get_run_manager),
) -> RunStatus:
    return manager.get_status()


@router.post("/current/stop", response_model=RunStatus)
async def stop_run(
    manager: RunManager = Depends(get_run_manager),
) -> RunStatus:
    return await manager.stop()


@router.get("", response_model=list[RunSummary])
async def list_runs(
    limit: int = 20,
    repo: SQLAlchemyRepository = Depends(get_repository),
) -> list[RunSummary]:
    rows = await repo.get_run_stats(limit=limit)
    return [
        RunSummary(
            id=row["id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            keywords=parse_search_keywords(row.get("keywords")),
            found=row.get("found", 0),
            applied=row.get("applied", 0),
            skipped=row.get("skipped", 0),
            failed=row.get("failed", 0),
            status=row.get("status", ""),
        )
        for row in rows
    ]


@router.get("/{run_id}/events")
async def stream_events(
    run_id: int,
    manager: RunManager = Depends(get_run_manager),
) -> EventSourceResponse:
    async def event_generator():
        async for event in manager.subscribe_events(run_id):
            yield {"event": event.get("type", "message"), "data": json.dumps(event)}

    return EventSourceResponse(event_generator())
