# System Handoff

Last updated: 2026-05-04

## Purpose

This repo is the second trading system. It should stay separate from the existing TQQQ alert bot.

Primary system:

- Existing repo: `tqqq-alert`
- Strategy: TQQQ long-only swing profit/re-entry system
- Status: live/open trade

Second system:

- New repo: `swing-stock-alert`
- Strategy: weekly top-2 swing momentum rotation
- Status: research/pilot candidate

## Recommended Operating Plan

Do now:

- Continue managing the current TQQQ position under the existing TQQQ rules.
- Use this repo to run weekly swing scans.
- Treat swing alerts as pilot signals until enough live/paper evidence accumulates.

Do not do yet:

- Do not replace TQQQ with the swing strategy.
- Do not force frequent short profit-taking. The backtest rejected that idea.

## Strategy Decision

The weekly top-2 swing rotation is the best stock-swing candidate found so far.

The pullback profit-taking system was tested because it matched the user's instinct to take short profits and recycle capital. It underperformed:

- Too many trades.
- Too little compounding.
- Winners were cut too mechanically.

The better active approach is:

- Buy the strongest stocks.
- Hold while strength continues.
- Sell when strength breaks.

## Current TQQQ Trade Context

From the current TQQQ repo state/strategy as of 2026-05-05:

- Ticker: `TQQQ`
- Avg cost: `$61.54`
- Shares: `40.4647`
- Entry date: `2026-04-29`
- Highest high since entry: about `$66.61`
- Active trailing stop: 25% below highest high since entry
- Profit target: sell all at +20% from average cost
- Re-buy trigger after profit exit: 7.5% pullback from profit sell price, or 20 trading days if still above SMA200
- Current mode: in position, not waiting for pullback

Recommendation as of 2026-05-05:

- Hold TQQQ under the current strategy.
- Do not manually take profit around a small gain.
- Let the strategy rules decide.

## Month-End Comparison Rule

The swing repo's automated TQQQ line is only a simple market reference from the pilot start date.

For the real winner calculation, inspect the `tqqq-alert` repo directly:

- `position_state.json`
- recent GitHub Actions runs
- any Telegram trade instructions
- current strategy code/commits

The TQQQ repo remains the source of truth for the real strategy.
