import os
import shutil
from datetime import UTC, datetime

from fastapi import APIRouter

from api.deps import state

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    db_ok = False
    db_size = 0
    try:
        if state.db_manager and state.db_manager.engine:
            async with state.db_manager.engine.connect() as conn:
                await conn.execute(conn.default_schema_name or "SELECT 1")
                db_ok = True
            db_path = state.settings.db_path
            if db_path.exists():
                db_size = db_path.stat().st_size
    except Exception:
        db_ok = False

    disk = shutil.disk_usage(state.settings.project_root)
    agent_proc = state.agent_process
    agent_alive = agent_proc is not None and agent_proc.poll() is None

    gemini_configured = bool(state.settings.ai.gemini_api_key) if state.settings else False

    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "2.0.0",
        "checks": {
            "database": {
                "status": "ok" if db_ok else "error",
                "size_bytes": db_size,
                "size_mb": round(db_size / (1024 * 1024), 2) if db_size else 0,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 1),
                "free_gb": round(disk.free / (1024**3), 1),
                "used_percent": round((disk.used / disk.total) * 100, 1),
            },
            "agent": {
                "status": "running" if agent_alive else "stopped",
                "pid": agent_proc.pid if agent_alive else None,
            },
            "gemini": {
                "configured": gemini_configured,
            },
        },
    }
