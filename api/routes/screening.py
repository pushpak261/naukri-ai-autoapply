"""Screening question management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import state

router = APIRouter(tags=["screening"])


class ScreeningAnswerUpdate(BaseModel):
    answer_text: str = Field(..., min_length=1, max_length=5000)


@router.get("/api/screening-questions")
async def list_screening_questions(
    status: str = Query("pending", max_length=20),
    search: str = Query("", max_length=200),
):
    if not state.repo:
        return {"items": [], "total": 0}
    items = await state.repo.list_screening_questions(status=status, search=search)
    return {"items": items, "total": len(items)}


@router.get("/api/screening-questions/stats")
async def screening_question_stats():
    if not state.repo:
        return {"pending": 0, "answered": 0, "total": 0, "total_failures": 0}
    return await state.repo.get_screening_question_stats()


@router.put("/api/screening-questions/{question_id}")
async def save_screening_answer(question_id: int, body: ScreeningAnswerUpdate):
    if not state.repo:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await state.repo.save_user_screening_answer(question_id, body.answer_text)
    if not result:
        raise HTTPException(status_code=404, detail="Screening question not found")
    return {"status": "saved", "item": result}


@router.delete("/api/screening-questions/{question_id}")
async def delete_screening_question(question_id: int):
    if not state.repo:
        raise HTTPException(status_code=503, detail="Database not available")
    deleted = await state.repo.delete_screening_question(question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Screening question not found")
    return {"status": "deleted", "id": question_id}
