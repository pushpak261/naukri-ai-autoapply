"""
Authentication endpoints: login, logout, refresh, and current user info.

Uses JWT access tokens (15 min) + refresh tokens (7 days, httpOnly cookie).
Refresh token hashes are persisted for rotation and revocation.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from fastapi import Depends

from api.auth.deps import get_current_user
from api.auth.jwt import (
    create_access_token,
    create_refresh_token,
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
    from api.auth.deps import _resolve_secret
    return _resolve_secret()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=os.environ.get("LOCAL_AGENT_MODE") != "1",
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/api/auth",
    )



def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
    )


@router.post("/api/auth/register")
async def register(body: RegisterRequest, response: Response):
    from api import identity
    import asyncio
    import re
    import sqlite3

    if os.environ.get("OPEN_REGISTRATION", "true").strip().lower() in ("0", "false", "no", "off"):
        raise HTTPException(403, "Public registration is disabled")
    email = body.email.strip().casefold()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "Enter a valid email address")
    if not 10 <= len(body.password) <= 128:
        raise HTTPException(422, "Password must contain 10 to 128 characters")
    if len(body.name) > 200:
        raise HTTPException(422, "Name is too long")
    try:
        user = await asyncio.to_thread(identity.create_user, email, body.password, body.name)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists") from None
    return await _issue_session(user, response)


async def _issue_session(user, response):
    import asyncio
    from api import identity
    secret = _get_jwt_secret()
    access_token = create_access_token(user['email'], secret)
    refresh_token = create_refresh_token(user['email'], secret)
    await asyncio.to_thread(identity.remember_session, user['id'], refresh_token)
    _set_refresh_cookie(response, refresh_token)
    return LoginResponse(access_token=access_token, email=user['email'])


@router.get("/api/auth/register/check")
async def check_registration():
    return {"registered": False, "email": "", "separate_accounts": True,
            "registration_enabled": os.environ.get("OPEN_REGISTRATION", "true").lower() not in ("0", "false", "no", "off")}


@router.post("/api/auth/login")
async def login(body: LoginRequest, response: Response):
    import asyncio
    from api import identity
    if not body.email.strip() or not body.password or len(body.password) > 128:
        raise HTTPException(422, "Email and password are required")
    user = await asyncio.to_thread(identity.authenticate, body.email, body.password)
    if user is None:
        raise HTTPException(401, "Invalid email or password")
    return await _issue_session(user, response)


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    import asyncio
    from api import identity
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token:
        await asyncio.to_thread(identity.revoke_session, token)
    _clear_refresh_cookie(response)
    return {"status": "ok", "message": "Logged out"}


@router.post("/api/auth/refresh")
async def refresh(request: Request, response: Response):
    import asyncio
    from api import identity
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    payload = verify_refresh_token(raw_token, _get_jwt_secret()) if raw_token else None
    user = await asyncio.to_thread(identity.consume_session, raw_token) if payload else None
    if user is None or user['email'] != payload.get('sub'):
        _clear_refresh_cookie(response)
        raise HTTPException(401, "Refresh token expired or invalid")
    issued = await _issue_session(user, response)
    return RefreshResponse(access_token=issued.access_token)


@router.get("/api/auth/me")
async def me(email: str = Depends(get_current_user)):
    return MeResponse(email=email, is_logged_in=True,
                      naukri_configured=bool(state.settings and state.settings.naukri.email))
