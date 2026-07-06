from datetime import UTC, datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
