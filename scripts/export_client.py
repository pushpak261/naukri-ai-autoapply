"""Create a source-only client handover without developer runtime data.

Run from any directory: python scripts/export_client.py
The original checkout, credentials, and working settings are never modified.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = {"api", "src", "libs", "services", "migrations", "tests", "monitoring"}
ROOT_FILES = {
    "README.md", "SECURITY.md", "LICENSE", "LICENSE.md", "NOTICE", "NOTICE.md",
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "alembic.ini",
    "Dockerfile", "Dockerfile.services", "docker-compose.yml", ".dockerignore",
    ".gitignore", ".python-version", ".env.example", "start-local.cmd",
}
SCRIPT_FILES = {"start-local.ps1", "local_dashboard.py", "export_client.py"}
DOC_FILES = {"CLIENT_HANDOVER.md", "LOCAL_MOBILE.md", "LOGIC_AUDIT.md"}
EXCLUDED_PARTS = {"node_modules", "dist", "__pycache__", ".venv", ".git", "local-workspace"}
EXCLUDED_SUFFIXES = {".enc", ".db", ".sqlite", ".sqlite3", ".pdf", ".log", ".pyc", ".png", ".jpg", ".jpeg"}


def include_file(name: str) -> bool:
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        return False
    if path.parts[0] == "data":
        return False
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if len(path.parts) == 1:
        return name in ROOT_FILES
    if path.parts[0] in SOURCE_DIRS:
        return True
    if path.parts[0] == "frontend":
        return path.parts[1] in {"src", "public", "tests"} or (len(path.parts) == 2 and path.suffix in {".json", ".ts", ".html"}) or name == "frontend/.env.example"
    if path.parts[0] == "scripts":
        return len(path.parts) == 2 and path.name in SCRIPT_FILES
    return path.parts[0] == "docs" and len(path.parts) == 2 and path.name in DOC_FILES


def client_config(platform: str) -> str:
    variable = platform.upper()
    return f'''# Client template: configure in the dashboard after registration.
{platform}:
  email: ${{{variable}_EMAIL:-}}
  password: ${{{variable}_PASSWORD:-}}
ai:
  use_gemini: false
  enable_matching: true
  gemini_api_key: ${{GEMINI_API_KEY:-}}
application:
  dry_run: true
  daily_cap: 10
  match_score_threshold: 70
  skip_external_apply: true
search:
  keywords: []
  locations: []
resume:
  path: data/resumes/resume.pdf
'''


def export_bundle(output: Path) -> int:
    if (ROOT / ".git").exists():
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    else:
        # A previously exported handover has no Git metadata.
        tracked = [name for name in ROOT_FILES if (ROOT / name).is_file()]
        for directory in SOURCE_DIRS | {"frontend", "scripts", "docs"}:
            for parent, directories, filenames in os.walk(ROOT / directory):
                directories[:] = [name for name in directories if name not in EXCLUDED_PARTS]
                tracked.extend((Path(parent) / name).relative_to(ROOT).as_posix() for name in filenames)
    # Include our newly authored handover files even before they are committed.
    candidates = set(tracked) | {"scripts/export_client.py", "tests/test_client_export.py", "docs/CLIENT_HANDOVER.md"}
    # New frontend files also belong in a working-tree preview of the release.
    candidates.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "frontend/src").rglob("*") if p.is_file())
    for directory in SOURCE_DIRS | {"frontend/tests", "docs"}:
        for parent, directories, filenames in os.walk(ROOT / directory):
            directories[:] = [name for name in directories if name not in EXCLUDED_PARTS]
            candidates.update((Path(parent) / name).relative_to(ROOT).as_posix() for name in filenames)
    files = sorted(name for name in candidates if include_file(name) and (ROOT / name).is_file())
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as bundle:
        for name in files:
            source = ROOT / name
            if source.is_symlink():
                raise ValueError(f"Refusing symlink in client export: {name}")
            content = source.read_bytes()
            # Remove the developer-specific fallback path from the shipped defaults.
            if name in {"src/naukri_agent/config/settings.py", "src/linked_agent/config/settings.py"}:
                import re
                content = re.sub(rb'data/resumes/[^"\r\n]+\.pdf', b'data/resumes/resume.pdf', content)
            bundle.writestr(name, content)
        bundle.writestr("config.yaml", client_config("naukri"))
        bundle.writestr("linkedin_config.yaml", client_config("linkedin"))
        bundle.writestr("HANDOVER.txt", "ApplyOS source handover\n\nStart with docs/CLIENT_HANDOVER.md and docs/LOCAL_MOBILE.md.\nPersonal data, existing accounts, resumes and sessions are excluded.\nDependencies and browser binaries must be installed on the client computer.\nReview licenses, source content, hosting and acceptance criteria before delivery.\n")
        bundle.writestr("RELEASE_MANIFEST.txt", "\n".join(files + ["config.yaml", "linkedin_config.yaml", "HANDOVER.txt"]) + "\n")
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/client/ApplyOS-source.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Output already exists; choose a new --output path: {output}")
    count = export_bundle(output)
    print(f"Exported {count} source files to {output}")
    print("Review RELEASE_MANIFEST.txt and complete docs/CLIENT_HANDOVER.md before client delivery.")


if __name__ == "__main__":
    main()
