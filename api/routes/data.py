import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

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
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/session/status")
async def session_status(
    platform: str = Query("naukri", max_length=50), account: str = Query("", max_length=255)
):
    import os
    import yaml

    # 1. Resolve Naukri session
    naukri_email = account or state.active_account_email
    naukri_valid = False
    naukri_cookie_count = 0
    naukri_last_modified = None

    if naukri_email:
        safe_name = naukri_email.replace("@", "_at_").replace(".", "_dot_")
        naukri_path = (
            state.settings.project_root / "data" / "sessions" / f"naukri_session_{safe_name}.json"
        )
    else:
        naukri_path = state.settings.project_root / "data" / "sessions" / "naukri_session.json"

    if not naukri_path.exists():
        fallback_path = state.settings.project_root / "data" / "sessions" / "naukri_session.json"
        if fallback_path.exists():
            naukri_path = fallback_path

    if naukri_path.exists():
        try:
            raw = naukri_path.read_bytes()
            decrypted = _try_decrypt_session(raw, state.settings)
            session_data = json.loads(decrypted.decode("utf-8"))
            cookies = session_data.get("cookies", [])
            naukri_cookies = [c for c in cookies if "naukri.com" in c.get("domain", "")]
            naukri_valid = len(naukri_cookies) > 0
            naukri_cookie_count = len(naukri_cookies)
            naukri_last_modified = datetime.fromtimestamp(
                naukri_path.stat().st_mtime, tz=UTC
            ).isoformat()
        except Exception:
            pass

    # 2. Resolve LinkedIn session
    linkedin_email = os.environ.get("LINKEDIN_EMAIL", "")
    if not linkedin_email:
        config_path = state.settings.project_root / "linkedin_config.yaml"
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
                    linkedin_email = config_data.get("linkedin", {}).get("email", "")
            except Exception:
                pass

    linkedin_valid = False
    linkedin_cookie_count = 0
    linkedin_last_modified = None

    if linkedin_email:
        safe_name = linkedin_email.replace("@", "_at_").replace(".", "_dot_")
        linkedin_path = (
            state.settings.project_root / "data" / "linkedin" / "sessions" / f"linkedin_session_{safe_name}.json"
        )
    else:
        linkedin_path = state.settings.project_root / "data" / "linkedin" / "sessions" / "linkedin_session.json"

    if not linkedin_path.exists():
        fallback_path = state.settings.project_root / "data" / "linkedin" / "sessions" / "linkedin_session.json"
        if fallback_path.exists():
            linkedin_path = fallback_path

    if linkedin_path.exists():
        try:
            raw = linkedin_path.read_bytes()
            decrypted = _try_decrypt_session(raw, state.settings)
            session_data = json.loads(decrypted.decode("utf-8"))
            cookies = session_data.get("cookies", [])
            linkedin_cookies = [c for c in cookies if "linkedin.com" in c.get("domain", "")]
            linkedin_valid = len(linkedin_cookies) > 0
            linkedin_cookie_count = len(linkedin_cookies)
            linkedin_last_modified = datetime.fromtimestamp(
                linkedin_path.stat().st_mtime, tz=UTC
            ).isoformat()
        except Exception:
            pass

    # 3. Determine active state based on active platform or running agent
    is_linkedin_running = False
    if state.agent_process:
        try:
            args = getattr(state.agent_process, "args", [])
            if any("linked_agent" in str(arg) for arg in args):
                is_linkedin_running = True
        except Exception:
            pass

    if is_linkedin_running or platform == "linkedin":
        exists = linkedin_path.exists()
        valid = linkedin_valid
        cookie_count = linkedin_cookie_count
        last_modified = linkedin_last_modified
    else:
        valid = naukri_valid or linkedin_valid
        cookie_count = naukri_cookie_count if naukri_valid else linkedin_cookie_count
        exists = naukri_path.exists() or linkedin_path.exists()
        last_modified = naukri_last_modified if naukri_valid else linkedin_last_modified

    # Create descriptive status message
    msg_parts = []
    msg_parts.append(f"Naukri: {'Active' if naukri_valid else 'Inactive'}")
    msg_parts.append(f"LinkedIn: {'Active' if linkedin_valid else 'Inactive'}")
    message = " | ".join(msg_parts)

    return {
        "exists": exists,
        "valid": valid,
        "cookie_count": cookie_count,
        "last_modified": last_modified,
        "message": message,
    }


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
async def clear_session(
    account: str = Query("", max_length=255), platform: str = Query("naukri", max_length=50)
):
    prefix = "linkedin_session" if platform == "linkedin" else "naukri_session"
    if platform == "linkedin":
        sessions_dir = state.settings.project_root / "data" / "linkedin" / "sessions"
    else:
        sessions_dir = state.settings.project_root / "data" / "sessions"

    if account:
        safe_name = account.replace("@", "_at_").replace(".", "_dot_")
        session_path = sessions_dir / f"{prefix}_{safe_name}.json"
    else:
        session_path = sessions_dir / f"{prefix}.json"

    if session_path.exists():
        session_path.unlink()
    return {
        "status": "cleared",
        "message": f"{platform.capitalize()} session cleared. Agent will need to re-login.",
    }


@router.get("/api/sessions/list")
async def list_sessions():
    naukri_dir = state.settings.project_root / "data" / "sessions"
    linkedin_dir = state.settings.project_root / "data" / "linkedin" / "sessions"
    sessions = []

    if naukri_dir.exists():
        # Naukri sessions
        for f in sorted(naukri_dir.glob("naukri_session*.json"), reverse=True):
            size = f.stat().st_size
            modified = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()
            name = f.stem.replace("naukri_session_", "")
            if name == "":
                name = "default"
            sessions.append(
                {
                    "name": f"Naukri ({name})",
                    "file": f.name,
                    "size": size,
                    "modified": modified,
                }
            )

    if linkedin_dir.exists():
        # LinkedIn sessions
        for f in sorted(linkedin_dir.glob("linkedin_session*.json"), reverse=True):
            size = f.stat().st_size
            modified = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()
            name = f.stem.replace("linkedin_session_", "")
            if name == "":
                name = "default"
            sessions.append(
                {
                    "name": f"LinkedIn ({name})",
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


@router.delete("/api/data/clear-all")
async def clear_all_data():
    """Clear all data from SQLite DB, cache files, sessions, and logs."""
    import os
    from pathlib import Path

    project_root = state.settings.project_root
    cleared_items = []
    errors = []

    # 1. Drop all tables and recreate them (Naukri DB)
    from src.naukri_agent.models.db_schema import Base as NaukriBase
    from src.naukri_agent.models.db_schema import _run_migrations

    try:
        async with state.db_manager.engine.begin() as conn:
            await conn.run_sync(NaukriBase.metadata.drop_all)
            await conn.run_sync(NaukriBase.metadata.create_all)
            await conn.run_sync(_run_migrations)
        cleared_items.append("Naukri database tables reset")
    except Exception as e:
        errors.append(f"Naukri database reset failed: {e}")

    # 1b. Drop and recreate LinkedIn DB tables if the file exists
    linkedin_db_path = project_root / "data" / "linkedin" / "linkedin_agent.db"
    if linkedin_db_path.exists():
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            from src.linked_agent.models.db_schema import Base as LinkedInBase

            linkedin_engine = create_async_engine(
                f"sqlite+aiosqlite:///{linkedin_db_path}",
                echo=False,
                connect_args={"check_same_thread": False},
            )
            async with linkedin_engine.begin() as conn:
                await conn.run_sync(LinkedInBase.metadata.drop_all)
                await conn.run_sync(LinkedInBase.metadata.create_all)
            await linkedin_engine.dispose()
            cleared_items.append("LinkedIn database tables reset")
        except Exception as e:
            errors.append(f"LinkedIn database reset failed: {e}")

    # 2. Reinitialize the repository (clear in-memory caches)
    try:
        await state.repo.initialize()
        cleared_items.append("Repository caches reset")
    except Exception as e:
        errors.append(f"Repository reinit failed: {e}")

    # 3. Clear cache JSON files
    cache_files = [
        project_root / "data" / "match_cache.json",
        project_root / "data" / "qa_cache.json",
        project_root / "data" / "linkedin" / "linkedin_match_cache.json",
        project_root / "data" / "logs" / ".alert_cooldowns.json",
        project_root / "data" / "logs" / "metrics.json",
    ]
    for cache_file in cache_files:
        if cache_file.exists():
            try:
                os.remove(cache_file)
                cleared_items.append(f"Deleted cache: {cache_file.relative_to(project_root)}")
            except Exception:
                pass

    # 4. Clear session files
    session_dirs = [
        project_root / "data" / "sessions",
        project_root / "data" / "linkedin" / "sessions",
    ]
    for s_dir in session_dirs:
        if s_dir.exists():
            for p in s_dir.glob("*.json*"):
                try:
                    os.remove(p)
                    cleared_items.append(f"Deleted session: {p.relative_to(project_root)}")
                except Exception:
                    pass

    # 5. Clear log files
    log_dir = project_root / "data" / "logs"
    if log_dir.exists():
        for p in log_dir.glob("*.log"):
            try:
                os.remove(p)
                cleared_items.append(f"Deleted log: {p.relative_to(project_root)}")
            except Exception:
                pass

    if errors:
        return {
            "status": "partial",
            "message": "Some items could not be cleared",
            "details": cleared_items,
            "errors": errors,
        }

    return {
        "status": "cleared",
        "message": "All data cleared successfully",
        "details": cleared_items,
    }
