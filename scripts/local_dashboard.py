"""Launch the local dashboard. Windows setup is provided by start-local.cmd."""
import argparse
import base64
import os
from pathlib import Path
import secrets
import socket
import sys
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def prepare_workspace(workspace):
    workspace.mkdir(parents=True, exist_ok=True)
    defaults = {
        "config.yaml": "naukri:\n  email: ''\n  password: ''\nai:\n  use_gemini: false\napplication:\n  dry_run: true\nresume:\n  path: ''\nexclusions:\n  legacy_domain_filter: false\n",
        "linkedin_config.yaml": "linkedin:\n  email: ''\n  password: ''\nai:\n  use_gemini: false\napplication:\n  dry_run: true\n",
    }
    for name, content in defaults.items():
        path = workspace / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    key = workspace / ".session_key"
    if not key.exists():
        key.write_text(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), encoding="ascii")
        key.chmod(0o600)
    return key.read_text().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8005)
    args = parser.parse_args()
    workspace = ROOT / "local-workspace"
    key = prepare_workspace(workspace)
    os.environ.update(LOCAL_AGENT_MODE="1", HEADLESS="false", AGENT_WORKSPACE=str(workspace),
                      DASHBOARD_DATA_DIR=str(workspace / "data"), SESSION_ENCRYPTION_KEY=key,
                      WEB_CONCURRENCY="1", MAX_ACTIVE_AGENTS="1")
    # Ignore cloud credentials inherited from a developer shell.
    for name in list(os.environ):
        if name.startswith(("NAUKRI_", "LINKEDIN_", "GEMINI_", "JWT_")) or name == "DASHBOARD_API_KEY":
            os.environ.pop(name)
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise SystemExit("Build the dashboard first: cd frontend && npm ci && npm run build")
    print(f"Computer dashboard: http://localhost:{args.port}", flush=True)
    addresses = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))
            addresses.add(probe.getsockname()[0])
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    for address in sorted(addresses):
        if not address.startswith("127."):
            print(f"Phone dashboard (same Wi-Fi): http://{address}:{args.port}", flush=True)
    print("Keep this window open. Register a local dashboard account; upload your resume; save your LinkedIn email.\nStart LinkedIn in dry-run mode and sign in manually in the browser on this computer.\nUse trusted private Wi-Fi only; allow Windows Firewall on Private networks if prompted. Do not forward this port to the internet.", flush=True)
    webbrowser.open(f"http://localhost:{args.port}")
    import uvicorn
    uvicorn.run("api.local:create_app", factory=True, host="0.0.0.0", port=args.port, workers=1)


if __name__ == "__main__":
    main()
