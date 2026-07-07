"""Run the FastAPI API (use ``python -m backend`` from the repo root)."""

from __future__ import annotations

import sys

import uvicorn


def main() -> None:
    # Uvicorn --reload on Windows can leave the listener in a broken state
    # (WinError 87) where connections hang indefinitely.
    use_reload = sys.platform != "win32"
    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=use_reload,
        loop="backend.loop:create_event_loop",
    )


if __name__ == "__main__":
    main()
