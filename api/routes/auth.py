"""
Authentication endpoints: login, logout, refresh, and current user info.

Uses JWT access tokens (15 min) + refresh tokens (7 days, httpOnly cookie).
The refresh token is encrypted on disk so the session survives server restarts.
"""

from __future__ import annotations

import secrets

import yaml
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from fastapi import Depends

from api.auth.deps import get_current_user
from api.auth.jwt import (
    create_access_token,
    create_refresh_token,
    delete_refresh_token,
    load_refresh_token,
    save_refresh_token,
    verify_refresh_token,
)
from api.deps import state

router = APIRouter(tags=["auth"])

REFRESH_COOKIE_NAME = "naukri_refresh_token"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    email: str
    is_logged_in: bool
    naukri_configured: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_jwt_secret() -> str:
    if state.settings and state.settings.jwt_secret:
        return state.settings.jwt_secret
    # Persist a generated secret so it survives across calls
    secret_file = state.settings.data_dir / ".jwt_secret" if state.settings else None
    if secret_file and secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    if secret_file:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secret, encoding="utf-8")
    return secret


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,  # Set True in production with HTTPS
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
    )


def _save_naukri_credentials(email: str, password: str) -> None:
    """Persist Naukri credentials to config.yaml so the agent can use them."""
    config_path = state.settings.project_root / "config.yaml"
    config_data: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

    config_data.setdefault("naukri", {})
    config_data["naukri"]["email"] = email
    config_data["naukri"]["password"] = password

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/auth/register")
async def register(body: RegisterRequest, response: Response):
    """Register a new user and persist credentials for the agent."""
    email = body.email.strip()
    password = body.password

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email and password are required",
        )

    try:
        _save_naukri_credentials(email, password)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {exc}",
        )

    secret = _get_jwt_secret()
    access_token = create_access_token(email, secret)
    refresh_token = create_refresh_token(email, secret)

    save_refresh_token(state.settings, refresh_token)
    _set_refresh_cookie(response, refresh_token)

    return LoginResponse(access_token=access_token, email=email)


@router.get("/api/auth/register/check")
async def check_registration():
    """Check if credentials are already configured (soft registration check)."""
    s = state.settings
    return {
        "registered": bool(s.naukri.email) if s else False,
        "email": s.naukri.email[:3] + "..." if s and s.naukri.email else "",
    }


@router.post("/api/auth/login")
async def login(body: LoginRequest, response: Response):
    """Authenticate with Naukri email + password.

    Stores credentials in config.yaml for the agent, issues a JWT access
    token (returned in the body) and a refresh token (httpOnly cookie).
    """
    email = body.email.strip()
    password = body.password

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email and password are required",
        )

    # Persist credentials so the agent can use them later
    try:
        _save_naukri_credentials(email, password)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {exc}",
        )

    # Issue tokens
    secret = _get_jwt_secret()
    access_token = create_access_token(email, secret)
    refresh_token = create_refresh_token(email, secret)

    save_refresh_token(state.settings, refresh_token)
    _set_refresh_cookie(response, refresh_token)

    return LoginResponse(access_token=access_token, email=email)


@router.post("/api/auth/logout")
async def logout(response: Response):
    """Invalidate the current session."""
    delete_refresh_token(state.settings)
    _clear_refresh_cookie(response)
    return {"status": "ok", "message": "Logged out"}


@router.post("/api/auth/refresh")
async def refresh(request: Request, response: Response):
    """Issue a new access token using the refresh token cookie."""
    secret = _get_jwt_secret()

    # Try cookie first, then fall back to saved file
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raw_token = load_refresh_token(state.settings)

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
        )

    payload = verify_refresh_token(raw_token, secret)
    if payload is None:
        delete_refresh_token(state.settings)
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or invalid",
        )

    email: str = payload.get("sub", "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    # Rotate refresh token
    new_refresh = create_refresh_token(email, secret)
    save_refresh_token(state.settings, new_refresh)
    _set_refresh_cookie(response, new_refresh)

    access_token = create_access_token(email, secret)
    return RefreshResponse(access_token=access_token)


@router.get("/api/auth/me")
async def me(email: str = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    s = state.settings
    naukri_configured = bool(s.naukri.email) if s else False
    return MeResponse(
        email=email,
        is_logged_in=True,
        naukri_configured=naukri_configured,
    )
