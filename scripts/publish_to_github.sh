#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

repo_name="${1:-swing-stock-alert}"
visibility="${2:---private}"

gh auth status
gh repo create "$repo_name" "$visibility" --source=. --remote=origin --push
