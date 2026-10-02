"""Report code coverage the way SonarCloud computes it for this project.

Sonar's coverage metric only counts files that survive
``sonar.coverage.exclusions`` from ``sonar-project.properties``, so the raw
``coverage report`` total is misleading. This script applies the same
exclusion list and prints the per-file figures the quality gate sees.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mirrors sonar.coverage.exclusions in sonar-project.properties
COVERAGE_EXCLUSIONS = [
    "**/browser/**",
    "**/pages/**",
    "**/stealth.py",
    "**/interactions.py",
    "**/main.py",
    "src/linked_agent/**",
    "api/**",
    "services/**",
    "migrations/**",
    "libs/**",
    "scripts/**",
    "tests/**",
    "**/terminal_logging.py",
    "**/project_indexer.py",
]


def _strip_root(path: str) -> str:
    """Normalise a path so it is relative to the repository root.

    coverage.xml reports paths relative to the ``--cov`` root (``src/...``)
    while some Sonar patterns are written without that prefix.
    """
    posix = path.replace("\\", "/")
    return posix[len("src/") :] if posix.startswith("src/") else posix


def is_excluded(rel_path: str) -> bool:
    posix = _strip_root(rel_path)
    return any(fnmatch.fnmatch(posix, _strip_root(p)) for p in COVERAGE_EXCLUSIONS)


def main() -> int:
    xml_path = ROOT / "coverage.xml"
    if not xml_path.exists():
        subprocess.run(
            [sys.executable, "-m", "pytest", "--cov=src", "--cov-report=xml", "-q"],
            cwd=ROOT,
            check=True,
        )

    tree = ET.parse(xml_path)  # noqa: S314 - we generate this file ourselves
    total_lines = covered_lines = 0
    rows: list[tuple[float, int, int, str]] = []

    for cls in tree.iter("class"):
        filename = cls.get("filename", "").replace("\\", "/")
        if is_excluded(filename):
            continue
        for line in cls.iter("line"):
            # Sonar only counts lines carrying real code (coverage.py marks
            # comments/blank with hits="0" but branch="false" and no <statement>);
            # using hits>0 OR a nonzero "missed" marker is unreliable, so we
            # rely on coverage.py's own line model via hits.
            hits = int(line.get("hits", "0"))
            if line.get("branch") == "true":
                # A branch line is executable only if it also has a statement.
                continue
            total_lines += 1
            if hits > 0:
                covered_lines += 1
            else:
                rows.append((0.0, int(line.get("number", "0")), 0, filename))

    covered_pct = (covered_lines / total_lines * 100) if total_lines else 0.0
    print(f"Sonar-equivalent coverage: {covered_pct:.2f}%  ({covered_lines}/{total_lines})")
    print(f"Target 80% -> need {int(total_lines * 0.8 - covered_lines)} more covered lines\n")

    missed_by_file: dict[str, list[int]] = {}
    for _, number, _, filename in rows:
        missed_by_file.setdefault(filename, []).append(number)

    print("Uncovered lines by file (ranked):")
    for filename, numbers in sorted(missed_by_file.items(), key=lambda kv: -len(kv[1])):
        if len(numbers) < 3:
            continue
        shown = numbers[:40]
        suffix = " ..." if len(numbers) > 40 else ""
        print(f"  {len(numbers):>4}  {filename}  ->  {shown}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())