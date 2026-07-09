"""
REST endpoints for resume upload, parsing, and profile management.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from api.deps import state
from src.naukri_agent.ai.llm_provider import GeminiProvider
from src.naukri_agent.ai.resume_parser import ResumeParser
from src.naukri_agent.utils.helpers import CANONICAL_RESUME_NAME, hash_file

router = APIRouter(tags=["resume"])

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

PROFILE_JSON_PATH: Path | None = None


def _get_profile_json_path() -> Path:
    global PROFILE_JSON_PATH
    if PROFILE_JSON_PATH is None:
        PROFILE_JSON_PATH = state.settings.project_root / "resume_profile.json"
    return PROFILE_JSON_PATH


def _update_config_resume_path(new_rel_path: str) -> None:
    """Update resume.path in config.yaml so it persists across restarts."""
    config_path = state.settings.project_root / "config.yaml"
    if not config_path.exists():
        return
    try:
        content = config_path.read_text(encoding="utf-8")
        # Replace the path: value under the resume: section
        updated = re.sub(
            r"(?m)^(\s*resume:\s*\n\s+path:\s*).*$",
            rf"\1{new_rel_path}",
            content,
        )
        if updated != content:
            config_path.write_text(updated, encoding="utf-8")
        # Also update the runtime settings so validation passes immediately
        state.settings.resume.path = new_rel_path
    except Exception:
        pass


@router.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    ext = Path(file.filename or "resume.pdf").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    state.settings.ensure_dirs()
    dest_dir = state.settings.resumes_dir

    ext_map = {".pdf": ".pdf", ".docx": ".docx"}
    dest_ext = ext_map.get(ext, ".pdf")
    dest_path = dest_dir / (
        CANONICAL_RESUME_NAME if dest_ext == ".pdf" else f"resume{dest_ext}"
    )

    dest_path.write_bytes(contents)
    file_hash = hash_file(dest_path)

    cached_profile = None
    if state.repo:
        cached = await state.repo.get_cached_profile(file_hash)
        if cached:
            cached_profile = {
                "name": cached.name,
                "email": cached.email,
                "phone": cached.phone,
                "current_title": cached.current_title,
                "summary": cached.summary,
                "total_experience_years": cached.total_experience_years,
                "skills": cached.skills,
                "technical_skills": cached.technical_skills,
                "soft_skills": cached.soft_skills,
                "job_titles_held": cached.job_titles_held,
                "education": cached.education,
                "work_experience": cached.work_experience,
                "certifications": cached.certifications,
                "languages": cached.languages,
                "key_achievements": cached.key_achievements,
                "file_hash": cached.file_hash,
            }

    if cached_profile:
        profile_json_path = _get_profile_json_path()
        cached_profile["uploaded_file_path"] = str(dest_path)
        try:
            profile_json_path.write_text(
                json.dumps(cached_profile, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

        # Update config.yaml to persist the active resume path
        rel_path = str(dest_path.relative_to(state.settings.project_root)).replace("\\", "/")
        _update_config_resume_path(rel_path)

        return {"status": "cached", "profile": cached_profile, "file_path": str(dest_path)}

    api_key = state.settings.ai.gemini_api_key
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Gemini API key not configured. Set GEMINI_API_KEY in environment or config.",
        )

    llm = GeminiProvider(
        api_key=api_key,
        model_name=state.settings.ai.model or "gemini-2.5-flash",
    )

    parser = ResumeParser(llm_provider=llm, repository=state.repo, settings=state.settings)

    try:
        profile = await parser.parse(str(dest_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {e}")

    if not profile.name:
        raise HTTPException(
            status_code=422,
            detail="Resume parsing returned no name. The file may be unreadable, or the AI service "
            "encountered an error. Check that your GEMINI_API_KEY is valid and has quota remaining.",
        )

    profile_json_path = _get_profile_json_path()
    profile_dict = {
        "uploaded_file_path": str(dest_path),
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "current_title": profile.current_title,
        "summary": profile.summary,
        "total_experience_years": profile.total_experience_years,
        "skills": profile.skills,
        "technical_skills": profile.technical_skills,
        "soft_skills": profile.soft_skills,
        "job_titles_held": profile.job_titles_held,
        "education": [
            {
                "degree": e.get("degree") if isinstance(e, dict) else e.degree,
                "institution": e.get("institution") if isinstance(e, dict) else e.institution,
                "year": e.get("year") if isinstance(e, dict) else e.year,
            }
            for e in profile.education
        ],
        "work_experience": [
            {
                "title": w.get("title") if isinstance(w, dict) else w.title,
                "company": w.get("company") if isinstance(w, dict) else w.company,
                "duration": w.get("duration") if isinstance(w, dict) else w.duration,
                "highlights": w.get("highlights") if isinstance(w, dict) else w.highlights,
            }
            for w in profile.work_experience
        ],
        "certifications": profile.certifications,
        "languages": profile.languages,
        "key_achievements": profile.key_achievements,
        "file_hash": profile.file_hash,
    }

    try:
        profile_json_path.write_text(
            json.dumps(profile_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    # Update config.yaml to persist the active resume path
    rel_path = str(dest_path.relative_to(state.settings.project_root)).replace("\\", "/")
    _update_config_resume_path(rel_path)

    return {"status": "parsed", "profile": profile_dict, "file_path": str(dest_path)}


@router.put("/api/resume/profile")
async def save_resume_profile(data: dict):
    profile_json_path = _get_profile_json_path()

    # Preserve uploaded_file_path from the existing file if not in the new data
    if "uploaded_file_path" not in data and profile_json_path.exists():
        try:
            existing = json.loads(profile_json_path.read_text(encoding="utf-8"))
            if "uploaded_file_path" in existing:
                data["uploaded_file_path"] = existing["uploaded_file_path"]
        except Exception:
            pass

    try:
        profile_json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {e}")

    # Also update the DB cache to keep it in sync with the edited profile
    if state.repo and data.get("file_hash"):
        try:
            await state.repo.save_resume_profile(
                file_hash=data["file_hash"],
                file_path=data.get("uploaded_file_path", ""),
                parsed_json=json.dumps(data, ensure_ascii=False),
            )
        except Exception:
            pass

    return {"status": "saved", "profile": data}
