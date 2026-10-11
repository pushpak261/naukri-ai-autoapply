import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from api.deps import state

router = APIRouter(tags=["autopilot"])

AUTOPILOT_FILE = "autopilot_config.json"


def _get_config_path() -> Path:
    return state.settings.data_dir / AUTOPILOT_FILE


async def _load_config() -> dict:
    path = _get_config_path()
    if path.exists():
        try:
            text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            return json.loads(text)
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


async def _save_config(cfg: dict) -> None:
    path = _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, json.dumps(cfg, indent=2), encoding="utf-8")
    state.autopilot_config = cfg


@router.get("/api/autopilot/config")
async def get_autopilot_config():
    return await _load_config()


@router.put("/api/autopilot/config")
async def update_autopilot_config(data: dict[str, Any]):
    current = await _load_config()
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
            if key in ("schedule", "throttle") and isinstance(data[key], dict):
                current[key] = {**current[key], **data[key]}
            else:
                current[key] = data[key]
    from api.scheduler import validate_schedule
    if not isinstance(current["enabled"], bool) or not isinstance(current["schedule"], dict):
        raise HTTPException(422, "enabled must be boolean and schedule must be an object")
    for key in ("company_blacklist", "company_whitelist"):
        if not isinstance(current[key], list) or any(not isinstance(v, str) or not v.strip() for v in current[key]):
            raise HTTPException(422, f"{key} must contain company names")
    if not isinstance(current["throttle"], dict) or any(type(v) is not int or v < 0 for v in current["throttle"].values()):
        raise HTTPException(422, "Throttle values must be nonnegative integers")
    if not isinstance(current["tier_map"], dict) or any(v not in ("top_tier", "startup", "default") for v in current["tier_map"].values()):
        raise HTTPException(422, "Company tiers must be top_tier, startup or default")
    from api.priority_rules import parse_condition
    rules = current["priority_rules"]
    if not isinstance(rules, list):
        raise HTTPException(422, "priority_rules must be an array")
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("action") != "apply_immediately" or type(rule.get("enabled")) is not bool:
            raise HTTPException(422, "Priority rules require enabled and action apply_immediately")
        try:
            parse_condition(rule.get("condition"))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    validate_schedule(current["schedule"])
    await _save_config(current)
    return {"status": "saved", "message": "Auto-pilot configuration updated"}


@router.get("/api/autopilot/blacklist")
async def get_blacklist():
    cfg = await _load_config()
    return {
        "blacklist": cfg.get("company_blacklist", []),
        "whitelist": cfg.get("company_whitelist", []),
    }


@router.post("/api/autopilot/blacklist")
async def add_to_blacklist(data: dict[str, str]):
    cfg = await _load_config()
    company = data.get("company", "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name required")
    if company not in cfg["company_blacklist"]:
        cfg["company_blacklist"].append(company)
    await _save_config(cfg)
    return {"status": "added", "company": company, "blacklist": cfg["company_blacklist"]}


@router.delete("/api/autopilot/blacklist")
async def remove_from_blacklist(data: dict[str, str]):
    cfg = await _load_config()
    company = data.get("company", "").strip()
    cfg["company_blacklist"] = [c for c in cfg["company_blacklist"] if c != company]
    await _save_config(cfg)
    return {"status": "removed", "company": company, "blacklist": cfg["company_blacklist"]}


@router.post("/api/autopilot/whitelist")
async def add_to_whitelist(data: dict[str, str]):
    cfg = await _load_config()
    company = data.get("company", "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name required")
    if company not in cfg["company_whitelist"]:
        cfg["company_whitelist"].append(company)
    await _save_config(cfg)
    return {"status": "added", "company": company, "whitelist": cfg["company_whitelist"]}


@router.delete("/api/autopilot/whitelist")
async def remove_from_whitelist(data: dict[str, str]):
    cfg = await _load_config()
    company = data.get("company", "").strip()
    cfg["company_whitelist"] = [c for c in cfg["company_whitelist"] if c != company]
    await _save_config(cfg)
    return {"status": "removed", "company": company, "whitelist": cfg["company_whitelist"]}


@router.get("/api/autopilot/schedule")
async def get_schedule():
    cfg = await _load_config()
    return cfg.get("schedule", {})
