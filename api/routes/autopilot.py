import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from api.deps import state

router = APIRouter(tags=["autopilot"])

AUTOPILOT_FILE = "autopilot_config.json"


def _get_config_path() -> Path:
    return state.settings.project_root / "data" / AUTOPILOT_FILE


def _load_config() -> dict:
    path = _get_config_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "enabled": False,
        "schedule": {"type": "daily", "time": "09:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
        "throttle": {"top_tier_daily": 3, "startup_daily": 10, "default_daily": 5},
        "priority_rules": [
            {
                "condition": "match_score > 90 AND posted_hours < 24",
                "action": "apply_immediately",
                "enabled": True,
            },
        ],
        "company_blacklist": [],
        "company_whitelist": [],
        "tier_map": {},
    }


def _save_config(cfg: dict) -> None:
    path = _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    state.autopilot_config = cfg


@router.get("/api/autopilot/config")
async def get_autopilot_config():
    return _load_config()


@router.put("/api/autopilot/config")
async def update_autopilot_config(data: dict[str, Any]):
    current = _load_config()
    for key in (
        "enabled",
        "schedule",
        "throttle",
        "priority_rules",
        "company_blacklist",
        "company_whitelist",
        "tier_map",
    ):
        if key in data:
            current[key] = data[key]
    _save_config(current)
    return {"status": "saved", "message": "Auto-pilot configuration updated"}


@router.get("/api/autopilot/blacklist")
async def get_blacklist():
    cfg = _load_config()
    return {
        "blacklist": cfg.get("company_blacklist", []),
        "whitelist": cfg.get("company_whitelist", []),
    }


@router.post("/api/autopilot/blacklist")
async def add_to_blacklist(data: dict[str, str]):
    cfg = _load_config()
    company = data.get("company", "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name required")
    if company not in cfg["company_blacklist"]:
        cfg["company_blacklist"].append(company)
    _save_config(cfg)
    return {"status": "added", "company": company, "blacklist": cfg["company_blacklist"]}


@router.delete("/api/autopilot/blacklist")
async def remove_from_blacklist(data: dict[str, str]):
    cfg = _load_config()
    company = data.get("company", "").strip()
    cfg["company_blacklist"] = [c for c in cfg["company_blacklist"] if c != company]
    _save_config(cfg)
    return {"status": "removed", "company": company, "blacklist": cfg["company_blacklist"]}


@router.post("/api/autopilot/whitelist")
async def add_to_whitelist(data: dict[str, str]):
    cfg = _load_config()
    company = data.get("company", "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name required")
    if company not in cfg["company_whitelist"]:
        cfg["company_whitelist"].append(company)
    _save_config(cfg)
    return {"status": "added", "company": company, "whitelist": cfg["company_whitelist"]}


@router.delete("/api/autopilot/whitelist")
async def remove_from_whitelist(data: dict[str, str]):
    cfg = _load_config()
    company = data.get("company", "").strip()
    cfg["company_whitelist"] = [c for c in cfg["company_whitelist"] if c != company]
    _save_config(cfg)
    return {"status": "removed", "company": company, "whitelist": cfg["company_whitelist"]}


@router.get("/api/autopilot/schedule")
async def get_schedule():
    cfg = _load_config()
    return cfg.get("schedule", {})
