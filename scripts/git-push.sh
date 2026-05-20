#!/usr/bin/env bash
# Push without Cursor/VS Code askpass (broken when IDE credential socket is down).
set -euo pipefail
cd "$(dirname "$0")/.."
unset GIT_ASKPASS SSH_ASKPASS VSCODE_GIT_ASKPASS VSCODE_GIT_IPC_HANDLE
exec git push "$@"
