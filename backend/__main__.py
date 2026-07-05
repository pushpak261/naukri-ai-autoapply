"""Run the FastAPI API (use ``python -m backend`` from the repo root)."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop="backend.loop:create_event_loop",
    )


if __name__ == "__main__":
    main()
