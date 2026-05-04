#!/usr/bin/env python3
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

from research.swing_stock_strategy import (
    UNIVERSE,
    load_prices,
    load_universe,
    run_weekly_momentum_rotation,
    scan_pullback_profit_taker,
    scan_weekly_rotation,
)


PILOT_STATE_FILE = Path("pilot_state.json")
REPORTS_DIR = Path("reports")
LATEST_REPORT = REPORTS_DIR / "latest_report.md"
DEFAULT_PILOT_START = "2026-05-04"
MAX_POSITIONS = 2


def load_state():
    if PILOT_STATE_FILE.exists():
        with PILOT_STATE_FILE.open() as f:
            return json.load(f)

    return {
        "pilot_start": DEFAULT_PILOT_START,
        "initial_equity": 1.0,
        "swing_strategy": "weekly_top_2_momentum_rotation",
        "tqqq_reference": "TQQQ buy/hold reference from pilot start; live TQQQ bot remains source of truth",
        "last_run_at": None,
        "last_signal_date": None,
    }


def save_state(state):
    state["last_run_at"] = datetime.now(UTC).isoformat()
    PILOT_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def pct(value):
    return f"{value:.1%}"


def multiple(value):
    return f"{value:.2f}x"


def money(value):
    return f"${value:.2f}"


def tqqq_reference_from_start(start):
    try:
        df = load_prices("TQQQ")
    except Exception as exc:
        return {"error": str(exc)}
    rows = df[df.index >= datetime.fromisoformat(start).date()]
    if rows.empty:
        return {"error": f"No TQQQ rows available from {start}"}
    start_price = float(rows["Close"].iloc[0])
    latest_price = float(rows["Close"].iloc[-1])
    value = latest_price / start_price
    return {
        "start_date": rows.index[0].isoformat(),
        "latest_date": rows.index[-1].isoformat(),
        "start_price": start_price,
        "latest_price": latest_price,
        "value": value,
        "return": value - 1,
    }


def send_telegram(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram secrets missing; skipping send.")
        return

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=30,
    )
    response.raise_for_status()


def build_report(mode):
    state = load_state()
    pilot_start = state.get("pilot_start", DEFAULT_PILOT_START)
    data, qqq, errors = load_universe(UNIVERSE)
    rotation = run_weekly_momentum_rotation(data, qqq, pilot_start, MAX_POSITIONS)
    asof, rotation_signals = scan_weekly_rotation(data, qqq, limit=10)
    _, pullback_signals = scan_pullback_profit_taker(data, qqq, limit=5)
    tqqq = tqqq_reference_from_start(pilot_start)
    qqq_row = qqq.loc[asof]
    market_on = qqq_row["Close"] > qqq_row["SMA200"]

    state.update(
        {
            "last_signal_date": asof.isoformat(),
            "latest_swing_value": round(rotation["final"], 6),
            "latest_swing_return": round(rotation["final"] - 1, 6),
            "latest_swing_cagr": round(rotation["cagr"], 6),
            "latest_swing_maxdd": round(rotation["maxdd"], 6),
            "latest_tqqq_reference_value": round(tqqq["value"], 6) if tqqq and not tqqq.get("error") else None,
            "latest_tqqq_reference_return": round(tqqq["return"], 6) if tqqq and not tqqq.get("error") else None,
            "market_filter_on": bool(market_on),
            "top_rotation_candidates": [s["ticker"] for s in rotation_signals[:MAX_POSITIONS]],
            "data_errors": errors,
        }
    )
    save_state(state)

    lines = [
        f"# Swing Stock Pilot Report - {asof}",
        "",
        f"Mode: `{mode}`",
        f"Pilot start: `{pilot_start}`",
        "",
        "## Market Filter",
        "",
        f"- QQQ close: {money(float(qqq_row['Close']))}",
        f"- QQQ SMA200: {money(float(qqq_row['SMA200']))}",
        f"- Market filter: {'ON' if market_on else 'OFF'}",
        "",
        "## Pilot Performance",
        "",
        "| System | Value | Return | Max DD | Trades |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| Swing top-2 rotation | {multiple(rotation['final'])} | "
            f"{pct(rotation['final'] - 1)} | {pct(rotation['maxdd'])} | {rotation['trades']} |"
        ),
    ]

    if tqqq and not tqqq.get("error"):
        lines.append(
            f"| TQQQ reference | {multiple(tqqq['value'])} | {pct(tqqq['return'])} | n/a | live bot owns exits |"
        )

    leader = "n/a"
    if tqqq and not tqqq.get("error"):
        leader = "Swing" if rotation["final"] > tqqq["value"] else "TQQQ reference"
    lines.extend(
        [
            "",
            f"Current leader since pilot start: **{leader}**",
            "",
            "## Weekly Rotation Candidates",
            "",
        ]
    )

    if not rotation_signals:
        lines.append("No weekly rotation candidates. Stay in cash for swing pilot.")
    else:
        lines.extend(
            [
                "| Rank | Ticker | Close | Initial Stop | 63d Return | 20d Return |",
                "| ---: | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for idx, signal in enumerate(rotation_signals[:MAX_POSITIONS], start=1):
            lines.append(
                f"| {idx} | {signal['ticker']} | {money(signal['close'])} | "
                f"{money(signal['initial_stop'])} | {pct(signal['ret63'])} | {pct(signal['ret20'])} |"
            )

    lines.extend(["", "## Rejected Profit-Taking Pullback Scan", ""])
    if not pullback_signals:
        lines.append("No pullback profit-taking candidates.")
    else:
        lines.extend(
            [
                "These are tracked only for research. This strategy is not the recommended primary system.",
                "",
                "| Rank | Ticker | Close | Initial Stop | 63d RS | 20d Return |",
                "| ---: | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for idx, signal in enumerate(pullback_signals[:3], start=1):
            lines.append(
                f"| {idx} | {signal['ticker']} | {money(signal['close'])} | "
                f"{money(signal['initial_stop'])} | {pct(signal['rs63'])} | {pct(signal['ret20'])} |"
            )

    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This swing repo is a demo/pilot for the month.",
            "- The active TQQQ repo remains the source of truth for the open TQQQ trade.",
            "- This repo runs at low frequency to avoid competing with the TQQQ bot for Yahoo data.",
            "- Assume pilot actions are followed only for comparison tracking.",
        ]
    )

    if errors:
        lines.extend(["", "## Data Errors", "", "```json", json.dumps(errors, indent=2), "```"])
    if tqqq and tqqq.get("error"):
        lines.extend(["", "## TQQQ Reference Error", "", "```", tqqq["error"], "```"])

    report = "\n".join(lines) + "\n"
    REPORTS_DIR.mkdir(exist_ok=True)
    LATEST_REPORT.write_text(report)
    history_path = REPORTS_DIR / f"{asof}.md"
    history_path.write_text(report)
    return report, rotation_signals, tqqq, rotation


def telegram_summary(report, rotation_signals, tqqq, rotation):
    top = ", ".join(s["ticker"] for s in rotation_signals[:MAX_POSITIONS]) or "none"
    tqqq_line = "TQQQ reference unavailable"
    if tqqq and not tqqq.get("error"):
        tqqq_line = f"TQQQ reference: {multiple(tqqq['value'])} ({pct(tqqq['return'])})"

    return (
        "📊 Swing stock pilot report\n"
        f"Top weekly candidates: {top}\n"
        f"Swing pilot: {multiple(rotation['final'])} ({pct(rotation['final'] - 1)})\n"
        f"{tqqq_line}\n"
        "Full report committed to reports/latest_report.md"
    )


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("RUN_MODE", "weekly")
    report, rotation_signals, tqqq, rotation = build_report(mode)
    print(report)
    send_telegram(telegram_summary(report, rotation_signals, tqqq, rotation))


if __name__ == "__main__":
    main()
