#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

repo="${1:-alonmorad9/swing-stock-alert}"

echo "Checking GitHub CLI auth..."
gh auth status

echo
echo "Setting GitHub Actions secrets for ${repo}."
echo "Paste each value when prompted. Input is hidden by your terminal."
echo

read -rsp "TELEGRAM_TOKEN: " telegram_token
echo
read -rsp "TELEGRAM_CHAT_ID: " telegram_chat_id
echo

printf '%s' "$telegram_token" | gh secret set TELEGRAM_TOKEN --repo "$repo"
printf '%s' "$telegram_chat_id" | gh secret set TELEGRAM_CHAT_ID --repo "$repo"

echo
echo "Secrets now configured:"
gh secret list --repo "$repo"

echo
echo "Triggering manual weekly workflow test..."
gh workflow run main.yml --repo "$repo" -f mode=weekly

echo
echo "Done. Watch the run here:"
echo "https://github.com/${repo}/actions"
