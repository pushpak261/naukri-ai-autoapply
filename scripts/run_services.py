"""
Local development runner for the Naukri microservice platform.

Starts every service as its own uvicorn process (true separate processes,
just like production) and wires them to a single shared database. Useful when
you don't want to spin up Docker.

Usage:
    python scripts/run_services.py                # all services, SQLite by default
    DATABASE_URL=postgresql+asyncpg://... python scripts/run_services.py
    python scripts/run_services.py --only gateway,auth,ai
    python scripts/run_services.py --no-gateway

Press Ctrl+C to stop everything.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

SERVICES = {
    "gateway": 8000,
    "auth": 8101,
    "config": 8102,
    "jobs": 8103,
    "resume": 8104,
    "applications": 8105,
    "ai": 8106,
    "agent": 8107,
    "data": 8108,
}

# Service key -> importable uvicorn module (handles folders whose names differ
# from the public service key, e.g. "data" lives in services/data_ops).
SERVICE_MODULES = {
    "data": "data_ops",
}


def build_env(port: int) -> dict[str, str]:
    env = dict(os.environ)
    # One shared DB for all local processes.
    env.setdefault(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{os.path.join(os.getcwd(), 'data', 'naukri_agent.db')}",
    )
    # Point every service at its siblings on localhost.
    for name, p in SERVICES.items():
        env[f"{name.upper()}_SERVICE_URL"] = f"http://localhost:{p}"
    env["GATEWAY_PORT"] = str(SERVICES["gateway"])
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Naukri microservices locally")
    parser.add_argument(
        "--only", help="Comma-separated service names to run (default: all)"
    )
    parser.add_argument("--no-gateway", action="store_true", help="Skip the gateway")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn --reload")
    args = parser.parse_args()

    wanted = set(SERVICES)
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip() in SERVICES}
    if args.no_gateway:
        wanted.discard("gateway")

    procs: list[subprocess.Popen] = []

    def shutdown(*_):
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        for name, port in SERVICES.items():
            if name not in wanted:
                continue
            module = SERVICE_MODULES.get(name, name)
            cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                f"services.{module}.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
            ]
            if args.reload:
                cmd.append("--reload")
            print(f"[run_services] starting {name} on :{port}")
            procs.append(
                subprocess.Popen(cmd, env=build_env(port))
            )
        print(f"[run_services] {len(procs)} services up. Gateway: http://localhost:8000")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
        print("[run_services] stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
