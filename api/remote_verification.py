"""One authenticated, short-lived browser controlled manually by its owner."""
import asyncio
import base64
import json
import os
import re
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Literal

from api.auth.deps import get_current_user
from api.deps import current_runtime
from src.linked_agent.browser.engine import LinkedInPlaywrightEngine
from src.linked_agent.browser.pages.login import LinkedInLoginPage
from src.linked_agent.config.settings import Settings
from libs.common.workspace_config import load_linkedin_workspace_config

router = APIRouter(prefix="/api/linkedin/verification", tags=["LinkedIn verification"])
ALLOWED_HOSTS = ("linkedin.com", "licdn.com", "google.com", "gstatic.com", "recaptcha.net", "arkoselabs.com", "hcaptcha.com")


def allowed_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == domain or host.endswith("." + domain) for domain in ALLOWED_HOSTS)


def settings_for_current_user():
    runtime = current_runtime()
    root = runtime.settings.project_root
    config = load_linkedin_workspace_config(root)
    email = config.get("linkedin", {}).get("email") or (os.getenv("LINKEDIN_EMAIL") if not runtime.user_id else "")
    if not email or len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "Save a valid LinkedIn email first.")
    key = os.getenv("SESSION_ENCRYPTION_KEY")
    if not key:
        raise HTTPException(503, "A stable SESSION_ENCRYPTION_KEY must be configured before saving browser sessions.")
    config.setdefault("linkedin", {})["email"] = email
    data = root / "data/linkedin"
    config.update(project_root=root, data_dir=data, sessions_dir=data / "sessions",
                  resumes_dir=root / "data/resumes", session_encryption_key=key)
    return Settings(**config)


class BrowserController:
    def __init__(self):
        self.owner = None
        self.engine = None
        self.phase = "closed"
        self.error = None
        self.task = None
        self.expiry = None
        self.lock = asyncio.Lock()
        self.cached_frame = None
        self.frame_time = 0

    def active(self):
        return self.phase in ("starting", "ready")

    def check_owner(self, owner):
        if self.owner != owner:
            raise HTTPException(404, "No verification browser for this account.")

    async def close(self, phase="closed"):
        for task in (self.task, self.expiry):
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if self.engine:
            await self.engine.close()
        self.engine = None
        self.cached_frame = None
        self.phase = phase

    async def launch(self, settings):
        try:
            self.engine = LinkedInPlaywrightEngine(settings, headless_override=True)
            page = await self.engine.launch()
            await page.set_viewport_size({"width": 480, "height": 800})
            async def restrict(route):
                if allowed_url(route.request.url):
                    await route.continue_()
                else:
                    await route.abort()
            await self.engine._context.route("**/*", restrict)
            await page.goto("https://www.linkedin.com/login", wait_until="commit", timeout=90_000)
            self.phase = "ready"
        except asyncio.CancelledError:
            raise
        except Exception:
            self.error = "Browser could not open LinkedIn. Close it and try again."
            await self.close("error")

    async def expire(self):
        await asyncio.sleep(600)
        async with self.lock:
            self.error = "Verification expired after 10 minutes. Start again."
            await self.close("expired")


controller = BrowserController()


class BrowserInput(BaseModel):
    action: Literal["click", "text", "key", "scroll", "reload", "clear"]
    x: int = Field(default=0, ge=0, le=479)
    y: int = Field(default=0, ge=0, le=799)
    text: str = Field(default="", max_length=500)
    key: Literal["Enter", "Tab", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"] = "Enter"
    delta: int = Field(default=0, ge=-800, le=800)


@router.post("/start")
async def start(owner=Depends(get_current_user)):
    from api.agent_runtime import _shared_lock, ensure_browser_capacity
    async with _shared_lock(), controller.lock:
        if controller.active():
            raise HTTPException(409, "A verification browser is already open. Close it first.")
        ensure_browser_capacity(maximum=1)
        settings = settings_for_current_user()
        controller.owner = owner
        controller.error = None
        controller.phase = "starting"
        controller.task = asyncio.create_task(controller.launch(settings))
        controller.expiry = asyncio.create_task(controller.expire())
        return {"phase": "starting"}


@router.get("/status")
async def status(owner=Depends(get_current_user)):
    controller.check_owner(owner)
    return {"phase": controller.phase, "error": controller.error}


@router.get("/frame")
async def frame(owner=Depends(get_current_user)):
    controller.check_owner(owner)
    async with controller.lock:
        if controller.phase != "ready":
            raise HTTPException(409, "Browser is not ready.")
        if controller.cached_frame is None or time.monotonic() - controller.frame_time > 2:
            controller.cached_frame = await controller.engine.page.screenshot(type="jpeg", quality=45)
            controller.frame_time = time.monotonic()
        return {"image": base64.b64encode(controller.cached_frame).decode(), "width": 480, "height": 800}


@router.post("/input")
async def browser_input(body: BrowserInput, owner=Depends(get_current_user)):
    controller.check_owner(owner)
    async with controller.lock:
        if controller.phase != "ready":
            raise HTTPException(409, "Browser is not ready.")
        page = controller.engine.page
        if body.action == "click":
            await page.mouse.click(body.x, body.y)
        elif body.action == "text":
            await page.keyboard.insert_text(body.text)
        elif body.action == "key":
            await page.keyboard.press(body.key)
        elif body.action == "scroll":
            await page.mouse.wheel(0, body.delta)
        elif body.action == "clear":
            await page.keyboard.press("ControlOrMeta+A")
            await page.keyboard.press("Backspace")
        else:
            await page.goto("https://www.linkedin.com/login", wait_until="commit", timeout=20_000)
        controller.cached_frame = None
        return {"status": "ok"}


@router.post("/finish")
async def finish(owner=Depends(get_current_user)):
    controller.check_owner(owner)
    async with controller.lock:
        if controller.phase != "ready":
            raise HTTPException(409, "Browser is not ready.")
        page = LinkedInLoginPage(controller.engine, None)
        verified, _ = await page.verify_auth_state()
        cookies = await controller.engine._context.cookies()
        if not verified or not any(c["name"] == "li_at" and c.get("value") for c in cookies):
            raise HTTPException(422, "LinkedIn login is not verified yet. Complete sign-in and verification in the browser view.")
        await controller.engine.save_session()
        await controller.close("verified")
        return {"phase": "verified"}


@router.post("/stop")
async def stop(owner=Depends(get_current_user)):
    controller.check_owner(owner)
    async with controller.lock:
        await controller.close()
    return {"phase": "closed"}


@router.get("/backup")
async def backup(owner=Depends(get_current_user)):
    engine = LinkedInPlaywrightEngine(settings_for_current_user())
    if not engine.has_saved_session():
        raise HTTPException(404, "No saved session. Verify LinkedIn first.")
    saved = json.loads(engine._decrypt(engine._session_path.read_bytes()))
    envelope = {"owner": owner, "email": engine._settings.linkedin.email.casefold(), "state": saved}
    return Response(engine._encrypt(json.dumps(envelope).encode()), media_type="application/octet-stream",
                    headers={"Content-Disposition": 'attachment; filename="linkedin-session.enc"'})


@router.post("/restore")
async def restore(file: UploadFile, owner=Depends(get_current_user)):
    from api.agent_runtime import _shared_lock, ensure_browser_capacity
    async with _shared_lock():
        ensure_browser_capacity(maximum=1)
        data = await file.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise HTTPException(413, "Session backup is too large.")
        engine = LinkedInPlaywrightEngine(settings_for_current_user())
        try:
            envelope = json.loads(engine._fernet.decrypt(data))
            if envelope["owner"] != owner or envelope["email"] != engine._settings.linkedin.email.casefold():
                raise ValueError()
            saved = envelope["state"]
            if not any(c.get("name") == "li_at" and c.get("value") for c in saved["cookies"]):
                raise ValueError()
            saved["cookies"] = [c for c in saved["cookies"] if any(c.get("domain", "").lstrip(".") == h or c.get("domain", "").endswith("." + h) for h in ALLOWED_HOSTS)]
            saved["origins"] = [o for o in saved.get("origins", []) if allowed_url(o.get("origin", ""))]
        except Exception:
            raise HTTPException(422, "Invalid backup or a different server encryption key.") from None
        engine._session_path.parent.mkdir(parents=True, exist_ok=True)
        engine._session_path.write_bytes(engine._encrypt(json.dumps(saved).encode()))
        return {"status": "restored", "message": "Session restored. LinkedIn may still request verification again."}
