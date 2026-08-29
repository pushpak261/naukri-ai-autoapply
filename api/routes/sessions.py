"""
Session management endpoints (moved out of the monolithic data router into the
Agent Orchestrator service, which owns browser session lifecycle).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import yaml
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, Query

from api.deps import state

router = APIRouter(tags=["sessions"])


@router.get("/api/session/status")
async def session_status(
    platform: str = Query("naukri", max_length=50), account: str = Query("", max_length=255)
):
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
            state.settings.project_root
            / "data"
            / "linkedin"
            / "sessions"
            / f"linkedin_session_{safe_name}.json"
        )
    else:
        linkedin_path = (
            state.settings.project_root / "data" / "linkedin" / "sessions" / "linkedin_session.json"
        )

    if not linkedin_path.exists():
        fallback_path = (
            state.settings.project_root / "data" / "linkedin" / "sessions" / "linkedin_session.json"
        )
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
        for f in sorted(naukri_dir.glob("naukri_session*.json"), reverse=True):
            size = f.stat().st_size
            modified = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()
            name = f.stem.replace("naukri_session_", "")
            if name == "":
                name = "default"
            sessions.append(
                {"name": f"Naukri ({name})", "file": f.name, "size": size, "modified": modified}
            )

    if linkedin_dir.exists():
        for f in sorted(linkedin_dir.glob("linkedin_session*.json"), reverse=True):
            size = f.stat().st_size
            modified = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat()
            name = f.stem.replace("linkedin_session_", "")
            if name == "":
                name = "default"
            sessions.append(
                {"name": f"LinkedIn ({name})", "file": f.name, "size": size, "modified": modified}
            )
    return {"items": sessions}
