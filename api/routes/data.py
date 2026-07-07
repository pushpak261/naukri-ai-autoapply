import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Query

from api.deps import state
from src.naukri_agent.models.db_schema import Job as DBJob
from src.naukri_agent.models.db_schema import Application as DBApplication

router = APIRouter(tags=["data"])


@router.get("/api/resume-profile")
async def get_resume_profile():
    profile_json_path = state.settings.project_root / "resume_profile.json"
    if not profile_json_path.exists():
        return {"exists": False, "profile": None}
    try:
        profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
        return {"exists": True, "profile": profile}
    except Exception:
        return {"exists": False, "profile": None}


@router.get("/api/cache/match-cache")
async def get_match_cache(search: str = Query("", max_length=200)):
    cache_path = state.settings.project_root / "data" / "match_cache.json"
    if not cache_path.exists():
        return {"items": [], "total": 0}
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
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
async def get_match_cache_stats():
    cache_path = state.settings.project_root / "data" / "match_cache.json"
    if not cache_path.exists():
        return {"total_entries": 0, "avg_score": 0, "would_apply": 0, "would_skip": 0}
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
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
async def clear_match_cache():
    cache_path = state.settings.project_root / "data" / "match_cache.json"
    if cache_path.exists():
        cache_path.write_text("{}", encoding="utf-8")
    return {"status": "cleared", "message": "Match cache cleared"}


@router.get("/api/metrics")
async def get_metrics():
    metrics_path = state.settings.project_root / "data" / "logs" / "metrics.json"
    if not metrics_path.exists():
        return {
            "total_runs": 0,
            "jobs_applied": 0,
            "jobs_failed": 0,
            "api_calls": 0,
            "duration_seconds": 0,
        }
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        return metrics
    except Exception:
        return {
            "total_runs": 0,
            "jobs_applied": 0,
            "jobs_failed": 0,
            "api_calls": 0,
            "duration_seconds": 0,
        }


@router.get("/api/logs")
async def list_logs():
    log_dir = state.settings.project_root / "data" / "logs"
    terminal_dir = state.settings.project_root / "terminal_output"
    files = []

    if log_dir.exists():
        for f in sorted(log_dir.glob("*.log"), reverse=True)[:20]:
            files.append(
                {
                    "name": f.name,
                    "path": str(f.relative_to(state.settings.project_root)),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
                    "type": "agent",
                }
            )
    if terminal_dir.exists():
        for f in sorted(terminal_dir.glob("*.log"), reverse=True)[:20]:
            files.append(
                {
                    "name": f.name,
                    "path": str(f.relative_to(state.settings.project_root)),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
                    "type": "terminal",
                }
            )

    return {"items": sorted(files, key=lambda x: x["modified"], reverse=True)}


@router.get("/api/logs/read")
async def read_log(log_path: str = Query(...), max_lines: int = Query(200, ge=1, le=5000)):
    full_path = state.settings.project_root / log_path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        total = len(lines)
        if total > max_lines:
            lines = lines[-max_lines:]
        return {
            "content": "\n".join(lines),
            "total_lines": total,
            "showing": len(lines),
            "name": full_path.name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/session/status")
async def session_status():
    session_path = state.settings.project_root / "data" / "sessions" / "naukri_session.json"
    if not session_path.exists():
        return {"exists": False, "valid": False, "message": "No saved session found"}
    try:
        raw = session_path.read_bytes()
        decrypted = _try_decrypt_session(raw, state.settings)
        session_data = json.loads(decrypted.decode("utf-8"))
        cookies = session_data.get("cookies", [])
        naukri_cookies = [c for c in cookies if "naukri.com" in c.get("domain", "")]
        now = datetime.now(UTC)
        return {
            "exists": True,
            "valid": len(naukri_cookies) > 0,
            "cookie_count": len(naukri_cookies),
            "last_modified": datetime.fromtimestamp(
                session_path.stat().st_mtime, tz=UTC
            ).isoformat(),
            "message": "Session valid" if naukri_cookies else "Session expired or invalid",
        }
    except Exception:
        return {"exists": True, "valid": False, "message": "Corrupted session file"}


def _fernet_for_settings(settings: Any) -> Fernet | None:
    key_str = settings.session_encryption_key
    if not key_str:
        seed = str(settings.project_root).encode("utf-8")
        key_str = base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode()
    try:
        return Fernet(key_str.encode() if isinstance(key_str, str) else key_str)
    except Exception:
        return None


def _try_decrypt_session(raw: bytes, settings: Any) -> bytes:
    fernet = _fernet_for_settings(settings)
    if fernet:
        try:
            return fernet.decrypt(raw)
        except Exception:
            pass
    return raw


@router.delete("/api/session")
async def clear_session(account: str = Query("", max_length=255)):
    if account:
        safe_name = account.replace("@", "_at_").replace(".", "_dot_")
        session_path = (
            state.settings.project_root / "data" / "sessions" / f"naukri_session_{safe_name}.json"
        )
    else:
        session_path = state.settings.project_root / "data" / "sessions" / "naukri_session.json"
    if session_path.exists():
        session_path.unlink()
    return {"status": "cleared", "message": "Session cleared. Agent will need to re-login."}


@router.get("/api/sessions/list")
async def list_sessions():
    sessions_dir = state.settings.project_root / "data" / "sessions"
    sessions = []
    if sessions_dir.exists():
        for f in sorted(sessions_dir.glob("naukri_session*.json"), reverse=True):
            size = f.stat().st_size
            modified = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()
            name = f.stem.replace("naukri_session_", "")
            if name == "":
                name = "default"
            sessions.append(
                {
                    "name": name,
                    "file": f.name,
                    "size": size,
                    "modified": modified,
                }
            )
    return {"items": sessions}


@router.get("/api/backups")
async def list_backups():
    backup_dir = state.settings.db_path.parent
    backups = []
    for f in sorted(backup_dir.glob("naukri_agent_backup_*.db"), reverse=True):
        backups.append(
            {
                "name": f.name,
                "size": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_ctime, tz=UTC).isoformat(),
            }
        )
    return {"items": backups}


@router.post("/api/backups/create")
async def create_backup():
    from src.naukri_agent.database.backup import DatabaseBackupService

    service = DatabaseBackupService(state.settings.db_path)
    service.backup()
    return {"status": "created", "message": "Database backup created"}


@router.post("/api/backups/restore")
async def restore_backup(name: str = Query(..., max_length=255)):
    """Restore database from a named backup file."""
    backup_dir = state.settings.db_path.parent
    backup_file = backup_dir / name
    if not backup_file.exists() or not name.startswith("naukri_agent_backup_"):
        raise HTTPException(status_code=404, detail=f"Backup '{name}' not found")

    import shutil
    from src.naukri_agent.utils.logger import log_info

    db_path = state.settings.db_path
    if db_path.exists():
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        pre_restore = db_path.parent / f"naukri_agent_pre_restore_{timestamp}.db"
        shutil.copy2(db_path, pre_restore)
        log_info(f"Pre-restore backup saved: {pre_restore.name}")

    shutil.copy2(backup_file, db_path)
    log_info(f"Database restored from backup: {name}")

    return {"status": "restored", "message": f"Database restored from '{name}'"}


@router.get("/api/export/full")
async def export_full_json():
    """Export all data as a single JSON file for backup/migration."""
    from sqlalchemy import select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        jobs_result = await session.execute(
            select(DBJob).order_by(DBJob.scraped_at.desc()).limit(1000)
        )
        jobs = jobs_result.scalars().all()

        apps_result = await session.execute(
            select(DBApplication).order_by(DBApplication.applied_at.desc()).limit(1000)
        )
        apps = apps_result.scalars().all()

        from src.naukri_agent.models.db_schema import ResumeProfile as DBResumeProfile

        profiles_result = await session.execute(
            select(DBResumeProfile).order_by(DBResumeProfile.parsed_at.desc()).limit(100)
        )
        profiles = profiles_result.scalars().all()

    def _serialize(obj):
        if hasattr(obj, "__table__"):
            cols = [c.name for c in obj.__table__.columns]
            return {
                c: (
                    getattr(obj, c).isoformat()
                    if hasattr(getattr(obj, c), "isoformat")
                    else getattr(obj, c)
                )
                for c in cols
            }
        return obj

    export = {
        "exported_at": datetime.now(UTC).isoformat(),
        "version": "2.0.0",
        "data": {
            "jobs": [_serialize(j) for j in jobs],
            "applications": [_serialize(a) for a in apps],
            "resume_profiles": [_serialize(p) for p in profiles],
        },
        "counts": {
            "jobs": len(jobs),
            "applications": len(apps),
            "resume_profiles": len(profiles),
        },
    }

    from fastapi.responses import JSONResponse

    return JSONResponse(
        content=export,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=naukri_agent_export.json"},
    )


@router.post("/api/import/full")
async def import_full_json(data: dict):
    """Import data from a full JSON export."""
    from src.naukri_agent.models.db_schema import ResumeProfile as DBResumeProfile

    session_factory = await state.db_manager.get_session_factory()
    imported_counts = {"jobs": 0, "applications": 0, "resume_profiles": 0}

    async with session_factory() as session:
        import_data = data.get("data", {})
        for job_data in import_data.get("jobs", []):
            existing = await session.execute(
                select(DBJob).where(DBJob.naukri_job_id == job_data.get("naukri_job_id", ""))
            )
            if existing.scalar_one_or_none():
                continue
            session.add(DBJob(**{k: v for k, v in job_data.items() if k != "id"}))
            imported_counts["jobs"] += 1

        for app_data in import_data.get("applications", []):
            existing = await session.execute(
                select(DBApplication).where(DBApplication.id == app_data.get("id", -1))
            )
            if existing.scalar_one_or_none():
                continue
            session.add(DBApplication(**{k: v for k, v in app_data.items() if k != "id"}))
            imported_counts["applications"] += 1

        for prof_data in import_data.get("resume_profiles", []):
            existing = await session.execute(
                select(DBResumeProfile).where(
                    DBResumeProfile.file_hash == prof_data.get("file_hash", "")
                )
            )
            if existing.scalar_one_or_none():
                continue
            session.add(DBResumeProfile(**{k: v for k, v in prof_data.items() if k != "id"}))
            imported_counts["resume_profiles"] += 1

        await session.commit()

    return {
        "status": "imported",
        "message": f"Imported {imported_counts['jobs']} jobs, {imported_counts['applications']} applications, {imported_counts['resume_profiles']} resume profiles",
        "counts": imported_counts,
    }


@router.get("/api/export/applications/csv")
async def export_applications_csv():
    """Export applications as CSV."""
    result = await state.repo.get_all_applications()
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "job_title",
            "company",
            "location",
            "match_score",
            "status",
            "applied_at",
            "error_message",
        ]
    )
    for app in result:
        writer.writerow(
            [
                app.get("id", ""),
                app.get("job_title", ""),
                app.get("company", ""),
                app.get("location", ""),
                app.get("match_score", ""),
                app.get("status", ""),
                app.get("applied_at", ""),
                app.get("error_message", ""),
            ]
        )
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


@router.get("/api/export/jobs/csv")
async def export_jobs_csv():
    """Export jobs as CSV."""
    from sqlalchemy import select

    session_factory = await state.db_manager.get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(DBJob).order_by(DBJob.scraped_at.desc()).limit(500))
        jobs = result.scalars().all()

    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["id", "title", "company", "location", "skills", "salary", "posted_date", "match_score"]
    )
    for j in jobs:
        writer.writerow(
            [j.id, j.title, j.company, j.location, j.skills, j.salary, j.posted_date, ""]
        )
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs.csv"},
    )


@router.get("/api/export/stats/json")
async def export_stats_json():
    """Export dashboard stats as JSON download."""
    from api.routes.stats import get_stats

    stats_data = await get_stats(365)
    from fastapi.responses import JSONResponse

    return JSONResponse(
        content=stats_data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=dashboard_stats.json"},
    )
