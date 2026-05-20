#!/usr/bin/env bash
# One-time GitHub auth for this server. Run in a normal terminal (not required after SSH key works).
set -euo pipefail

KEY="${HOME}/.ssh/id_ed25519.pub"
echo "=== SSH public key (add to GitHub) ==="
echo "Account key:  https://github.com/settings/ssh/new"
echo "Deploy key:   https://github.com/adrienqi/openclaw-mentor/settings/keys"
echo "(Deploy key: enable write access if you use a deploy key.)"
echo
cat "$KEY"
echo
echo "=== Or authenticate gh with a Personal Access Token (repo scope) ==="
echo "Create: https://github.com/settings/tokens?type=beta  (or classic with repo scope)"
echo "Then run:"
echo '  read -rs GITHUB_TOKEN; echo; printf "%s" "$GITHUB_TOKEN" | gh auth login --with-token'
echo '  gh ssh-key add ~/.ssh/id_ed25519.pub --title "openclaw-mentor-server"'
echo
echo "Test: ssh -T git@github.com"
echo "Push: ./scripts/git-push.sh --set-upstream openclaw-mentor main"
