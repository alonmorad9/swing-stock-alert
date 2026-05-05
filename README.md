# Swing Stock Alert

Second trading system research repo.

This repo is intentionally separate from the existing TQQQ alert bot. The TQQQ strategy remains the primary live system for the current open TQQQ trade. This repo tracks the second system: a stock swing strategy that scans liquid growth stocks, ranks the strongest names, and gives clear buy/sell rules.

## Recommended Strategy

Use the **weekly top-2 swing momentum rotation**.

Rules:

- Trade only when `QQQ` is above its 200-day simple moving average.
- Once per week after the final trading day, rank liquid growth stocks by:
  - 63-day momentum
  - 20-day momentum
  - strength above SMA50
- Buy the top 2 qualified stocks at the next trading day's open.
- Sell if:
  - the stock closes below EMA21,
  - the trailing stop is hit,
  - the stock drops out of the weekly top 2,
  - or QQQ closes below SMA200.

The tested profit-taking pullback strategy is documented, but it is **not recommended** as the primary system because it underperformed badly.

## Historical Proof

Main test window: 2018-01-01 through 2026-05-04.

| Strategy | Final | CAGR | Max DD | Calmar | Trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| Weekly top-2 swing momentum rotation | 16.5x | 40.0% | -39.5% | 1.01 | 480 |
| Old TQQQ live-like strategy at research time | 16.1x | 39.6% | -34.9% | 1.14 | 45 |
| TQQQ buy and hold | 11.3x | 33.8% | -81.7% | 0.41 | 1 |
| Best pullback profit-taking variant | 2.7x | 12.8% | -26.3% | 0.49 | 1,649 |

Conclusion:

- Keep managing the current open TQQQ trade under the TQQQ bot rules.
- The TQQQ strategy changed after initial swing research; the TQQQ repo is the source of truth for the real strategy.
- Run this swing system as a second, separate pilot.
- Do not replace the TQQQ strategy yet.

## Run Locally

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run the scanner and backtest:

```bash
python3 research/swing_stock_strategy.py --start 2018-01-01 --max-positions 2
```

Run the pilot report bot:

```bash
python3 script.py manual
```

Generated outputs:

- `research/out/weekly_rotation_current_signals.csv`
- `research/out/weekly_rotation_trades.csv`
- `research/out/weekly_rotation_equity_curve.csv`
- `research/out/pullback_profit_taker_current_signals.csv`

## Current Open TQQQ Context

The existing TQQQ bot strategy is documented in [docs/tqqq-strategy-context.md](docs/tqqq-strategy-context.md).

Current recommendation from the research conversation:

- Keep the open TQQQ trade.
- Do not manually take profit early.
- Sell only according to the TQQQ strategy: SMA200 break, trailing stop hit, or configured profit target.

## Automation

Automation is documented in [docs/automation.md](docs/automation.md).

The intended setup mirrors the TQQQ repo's safer pattern:

- Cloudflare Worker triggers GitHub Actions through `workflow_dispatch`.
- This repo runs weekly plus month-end only.
- The workflow commits `pilot_state.json` and report files so swing demo data is preserved.
- Month-end comparison must inspect the real TQQQ repo directly, because this repo only records a TQQQ market reference.

## Important Caveats

- This is research, not financial advice.
- Yahoo Finance data can be flaky.
- The swing stock universe uses current liquid growth names, so historical backtests have selection bias.
- The strategy should be paper traded or piloted with smaller capital before being treated like a live primary system.
