#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../scheduler/cloudflare"

echo "Deploying Cloudflare Worker..."
npx wrangler deploy

echo
echo "Set the Cloudflare Worker GITHUB_TOKEN secret."
echo "Use a GitHub fine-grained token with Actions: Read and write, Contents: Read, Metadata: Read"
echo "for alonmorad9/swing-stock-alert."
echo
npx wrangler secret put GITHUB_TOKEN

echo
echo "Cloudflare Worker deployed and secret configured."
