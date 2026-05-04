# Automation

Last updated: 2026-05-04

## Goal

Run the swing stock system as a low-frequency pilot without interfering with the active TQQQ bot.

## Frequency

This repo should run much less often than the TQQQ repo:

- Weekly scan: Friday 21:30 UTC, after regular US market close.
- Month-end comparison: 21:30 UTC on days 28-31.

This keeps Yahoo Finance requests low. The active TQQQ bot remains the priority because it manages a real open trade.

## GitHub Action

Workflow:

- `.github/workflows/main.yml`

Manual run:

```bash
gh workflow run main.yml -f mode=weekly
```

The workflow:

- installs dependencies,
- runs `script.py`,
- sends Telegram if secrets exist,
- commits `pilot_state.json`,
- commits `reports/latest_report.md`,
- commits dated reports in `reports/`.

Required repository secrets:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

## External Scheduler

The preferred scheduler is the same pattern as the TQQQ repo:

- Cloudflare Worker triggers GitHub Actions through `workflow_dispatch`.
- GitHub Actions is not relied on as the only scheduler.

Worker files:

- `scheduler/cloudflare/worker.js`
- `scheduler/cloudflare/wrangler.toml`

Required Cloudflare secret:

- `GITHUB_TOKEN`

The token needs permission to dispatch workflows in `alonmorad9/swing-stock-alert`.

## Month-End Comparison

Every run updates `pilot_state.json` with:

- latest swing pilot value,
- latest swing return,
- latest TQQQ reference value,
- latest TQQQ reference return,
- current leader.

At month end, ask Codex to inspect:

- `reports/latest_report.md`
- `reports/*.md`
- `pilot_state.json`

Assumption for the pilot:

- If the swing bot gave an instruction, assume the instruction was followed.
- The TQQQ repo remains the source of truth for the real TQQQ trade.
