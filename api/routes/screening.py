"""Review missing screening facts inside the authenticated tenant workspace."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.deps import state
from libs.common.screening_review import ScreeningReviewStore

router = APIRouter(tags=["screening"])


class ScreeningAnswers(BaseModel):
    answers: dict[str, Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        min_length=1, max_length=100
    )
    queue_jobs: bool = False


@router.get("/api/screening/questions")
async def screening_questions():
    store = ScreeningReviewStore(state.settings.project_root)
    return {"items": await asyncio.to_thread(store.pending)}


@router.put("/api/screening/answers")
async def save_screening_answers(body: ScreeningAnswers):
    store = ScreeningReviewStore(state.settings.project_root)
    try:
        jobs = await asyncio.to_thread(store.save_answers, body.answers)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    queued = 0
    if body.queue_jobs and jobs:
        from api.job_queue import enqueue_jobs

        session_factory = await state.db_manager.get_session_factory()
        for offset in range(0, len(jobs), 100):
            queued += await enqueue_jobs(session_factory, jobs[offset : offset + 100])
    return {
        "saved": len(body.answers),
        "queued": queued,
        "job_ids": jobs,
        "message": "Answers saved. Queued jobs use the normal filters, limits and submission checks.",
    }
