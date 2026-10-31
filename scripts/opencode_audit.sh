#!/usr/bin/env bash
# Whole-repository health audit used by the OpenCode GitHub integration.
#
# Hard failures mirror the required CI gates and trigger an automatic OpenCode
# fix. Full-repo ruff and mypy findings are advisory because the project tracks
# that pre-existing debt separately; they are reported but do not trigger a fix.
#
# Usage: scripts/opencode_audit.sh [report-path]
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPORT="${1:-opencode-audit.md}"
PYTHON="${PYTHON:-python}"
LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$LOG_DIR"' EXIT

export CI=1
export NO_COLOR=1

FAILURES=0
HARD_CHECKS=0
CHECKS=0

cat >"$REPORT" <<EOF
# OpenCode health audit

- Commit: \`$(git rev-parse --short HEAD 2>/dev/null || echo unknown)\`
- Date: $(date -u +'%Y-%m-%dT%H:%M:%SZ')
- Python: \`$($PYTHON --version 2>&1 | head -1)\`
EOF

run_check() {
  local mode="$1"
  local name="$2"
  shift 2
  local slug log
  slug="$(printf '%s' "$name" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')"
  log="$LOG_DIR/$slug.log"
  CHECKS=$((CHECKS + 1))
  if [ "$mode" = "hard" ]; then
    HARD_CHECKS=$((HARD_CHECKS + 1))
  fi

  printf '\n### %s\n\n' "$name" >>"$REPORT"
  if "$@" >"$log" 2>&1; then
    printf '✅ PASS\n' >>"$REPORT"
  else
    if [ "$mode" = "hard" ]; then
      FAILURES=$((FAILURES + 1))
      printf '❌ FAIL\n' >>"$REPORT"
    else
      printf '⚠️ ADVISORY FAILURE (pre-existing debt; does not trigger autofix)\n' >>"$REPORT"
    fi
    {
      printf '\n```text\n'
      tail -n 150 "$log"
      printf '```\n'
    } >>"$REPORT"
  fi
}

# Required gates, matching .github/workflows/ci.yml.
run_check hard "Hardening lint (ruff)" \
  "$PYTHON" -m ruff check \
  libs tests/test_resilience.py tests/test_security.py tests/test_auth_verify.py \
  tests/test_config_secret.py tests/test_apply_claim.py tests/test_block_detector.py
run_check hard "Hardening format (black)" "$PYTHON" -m black --check libs
run_check hard "Full Python test suite" "$PYTHON" -m pytest -q
run_check hard "Browser regression suite" "$PYTHON" -m pytest \
  tests/test_offline_workflows.py \
  tests/test_linkedin_modern_search.py \
  tests/test_linkedin_screening_flow.py \
  tests/test_linkedin_search_recovery.py \
  tests/test_linkedin_runtime_recovery.py \
  tests/test_screening_intelligence_browser.py \
  tests/test_apply_flow_audit.py \
  tests/test_naukri_production_flow.py \
  tests/test_offline_screening_completion.py \
  tests/test_naukri_search_loading.py \
  tests/test_naukri_chatbot_reliability.py \
  tests/test_naukri_pagination_boundaries.py \
  tests/test_external_applications.py \
  -q
run_check hard "Frontend lint" npm --prefix frontend run lint
run_check hard "Frontend production build" npm --prefix frontend run build
run_check hard "Frontend API tests" node frontend/tests/api.test.mjs

# Advisory checks. These are known pre-existing debt and are report-only.
run_check advisory "Full-repository ruff (advisory)" "$PYTHON" -m ruff check .
run_check advisory "Python type check (advisory)" "$PYTHON" -m mypy src/

printf '\n---\n\n' >>"$REPORT"
if [ "$FAILURES" -gt 0 ]; then
  printf '**%s of %s hard checks failed (%s checks total). OpenCode should fix the failures above.**\n' \
    "$FAILURES" "$HARD_CHECKS" "$CHECKS" >>"$REPORT"
  exit 1
fi

printf '**All %s hard checks passed (%s checks total, including advisory checks).**\n' \
  "$HARD_CHECKS" "$CHECKS" >>"$REPORT"
