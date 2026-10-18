import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Response
from sqlalchemy import text

from api.deps import state

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(response: Response):
    db_ok = False
    db_size = 0
    try:
        if state.db_manager and state.db_manager.engine:
            async with state.db_manager.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                db_ok = True
            db_path = Path(state.settings.db_path)
            if db_path.exists():
                db_size = db_path.stat().st_size
    except Exception:
        db_ok = False

    disk_ok = False
    disk_check = {"status": "error", "total_gb": 0, "free_gb": 0, "used_percent": 0}
    try:
        disk = shutil.disk_usage(state.settings.project_root if state.settings else Path.cwd())
        disk_ok = disk.total > 0
        if disk_ok:
            disk_check = {
                "status": "ok",
                "total_gb": round(disk.total / (1024**3), 1),
                "free_gb": round(disk.free / (1024**3), 1),
                "used_percent": round((disk.used / disk.total) * 100, 1),
            }
    except (OSError, TypeError, ValueError):
        pass
    agent_proc = state.agent_process
    agent_alive = agent_proc is not None and agent_proc.poll() is None

    gemini_configured = bool(state.settings.ai.gemini_api_key) if state.settings else False

    ready = db_ok and disk_ok
    response.status_code = 200 if ready else 503
    return {
        "status": "ok" if ready else "degraded",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "2.0.0",
        "checks": {
            "database": {
                "status": "ok" if db_ok else "error",
                "size_bytes": db_size,
                "size_mb": round(db_size / (1024 * 1024), 2) if db_size else 0,
            },
            "disk": disk_check,
            "agent": {
                "status": "running" if agent_alive else "stopped",
                "pid": agent_proc.pid if agent_alive else None,
            },
            "gemini": {
                "configured": gemini_configured,
            },
        },
    }

