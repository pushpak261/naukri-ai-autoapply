"""Private progress for a user-started run of exactly 100 Naukri applications."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

TARGET = 100
MAX_RUNTIME_SECONDS = 6 * 3600


def requested_target(process):
    args = getattr(process, "args", None)
    if not isinstance(args, (list, tuple)) or "src.naukri_agent.main" not in args:
        return 0
    try:
        return TARGET if args[args.index("--target") + 1] == str(TARGET) else 0
    except (ValueError, IndexError):
        return 0


def read_target_progress(root):
    try:
        value = json.loads((Path(root) / "data/naukri_run_target.json").read_text())
        return value if isinstance(value, dict) and value.get("target") == TARGET else None
    except (OSError, ValueError):
        return None


def write_target_progress(root, **values):
    path = Path(root) / "data/naukri_run_target.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    values.update(target=TARGET, pid=os.getpid(), updated_at=datetime.now(UTC).isoformat())
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(values), encoding="utf-8")
    temporary.replace(path)


def target_progress_for(root, process):
    progress = read_target_progress(root)
    if process is None:
        return progress
    if not requested_target(process):
        return None
    if progress and progress.get("pid") == process.pid:
        return progress
    return {"target": TARGET, "submitted": 0, "state": "starting", "reason": "Starting target run"}
