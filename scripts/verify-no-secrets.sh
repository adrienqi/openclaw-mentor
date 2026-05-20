#!/usr/bin/env bash
# Fail if staged or tracked files contain likely secrets. Run before commit/push.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "verify-no-secrets: not a git repository" >&2
  exit 1
fi

# Files to scan: index (staged) + working tree paths that would be added
mapfile -t FILES < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null; git ls-files 2>/dev/null | sort -u)
if [ "${#FILES[@]}" -eq 0 ]; then
  echo "verify-no-secrets: nothing to scan"
  exit 0
fi

BLOCKED_PATHS='\.env$|HA_CREDENTIALS\.txt$|/secrets\.yaml$|/\.storage/|/data/|\.sqlite|\.db$|\.pem$|\.key$'

PATTERNS=(
  'TELEGRAM_BOT_TOKEN=[0-9]+:[A-Za-z0-9_-]{20,}'
  'ANTHROPIC_API_KEY=sk-ant-api[0-9A-Za-z_-]{20,}'
  'HA_WEBHOOK_SECRET=[A-Za-z0-9]{16,}'
  'sk-ant-api03[A-Za-z0-9_-]{20,}'
  '[0-9]{8,}:[A-Za-z0-9_-]{30,}'  # Telegram bot token shape
)

fail=0
for f in "${FILES[@]}"; do
  [ -z "$f" ] && continue
  [ ! -f "$f" ] && continue
  if echo "$f" | grep -qE "$BLOCKED_PATHS"; then
    echo "BLOCKED PATH (must be gitignored): $f" >&2
    fail=1
    continue
  fi
  for pat in "${PATTERNS[@]}"; do
    if grep -qE "$pat" "$f" 2>/dev/null; then
      echo "SECRET PATTERN in $f (pattern: $pat)" >&2
      fail=1
    fi
  done
done

# Block committing real Tailscale IPs from this deployment (100.84.x.x documented in README)
if git ls-files README.md 2>/dev/null | grep -q .; then
  if grep -qE '100\.84\.71\.100' README.md 2>/dev/null; then
    echo "README.md contains deployment-specific Tailscale IP; use 100.x.y.z placeholder" >&2
    fail=1
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo "verify-no-secrets: FAILED" >&2
  exit 1
fi

echo "verify-no-secrets: OK (${#FILES[@]} files checked)"
