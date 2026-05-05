# Swing Stock Pilot Report - 2026-05-05

Mode: `manual`
Pilot start: `2026-05-04`

## Market Filter

- QQQ close: $680.57
- QQQ SMA200: $604.04
- Market filter: ON

## Pilot Performance

| System | Value | Return | Max DD | Trades |
| --- | ---: | ---: | ---: | ---: |
| Swing paper pilot | 1.05x | 4.6% | 0.0% | assumed followed |
| TQQQ market reference | 1.03x | 3.4% | n/a | not the real TQQQ bot |

## Paper Positions

| Ticker | Entry Date | Entry | Current | Return | Allocation |
| --- | --- | ---: | ---: | ---: | ---: |
| INTC | 2026-05-04 | $97.99 | $105.71 | 7.9% | 50.0% |
| MRVL | 2026-05-04 | $164.41 | $166.63 | 1.4% | 50.0% |

Current leader since pilot start: **Swing demo**

## Weekly Rotation Candidates

| Rank | Ticker | Close | Initial Stop | 63d Return | 20d Return |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | INTC | $105.71 | $93.02 | 114.6% | 99.8% |
| 2 | MRVL | $166.63 | $146.63 | 120.7% | 52.4% |

## Rejected Profit-Taking Pullback Scan

These are tracked only for research. This strategy is not the recommended primary system.

| Rank | Ticker | Close | Initial Stop | 63d RS | 20d Return |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | AMAT | $405.17 | $377.67 | 16.8% | 14.4% |
| 2 | ABNB | $138.91 | $131.20 | 3.3% | 11.2% |
| 3 | NVDA | $199.99 | $187.57 | 0.4% | 12.3% |

## Guardrails

- This swing repo is a demo/pilot for the month.
- Swing paper performance assumes the first reported candidates were bought for the demo.
- The active TQQQ repo remains the source of truth for the open TQQQ trade.
- The TQQQ value in this report is only a market reference from the pilot start date.
- For month-end winner calculation, inspect the real `tqqq-alert` repo state and strategy history.
- This repo runs at low frequency to avoid competing with the TQQQ bot for Yahoo data.
- Assume pilot actions are followed only for comparison tracking.
