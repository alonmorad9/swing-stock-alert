#!/usr/bin/env python3
"""Backtest and scan a clear stock swing strategy."""

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests


START_CASH = 1.0
CACHE_DIR = Path(tempfile.gettempdir()) / "swing_stock_strategy_cache"
PERIOD1 = 1262304000
PERIOD2 = 4102444800

# Current, liquid, growth-heavy universe for today's scanner.
# This is deliberately explicit so live signals do not change because a website table changed.
UNIVERSE = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA", "NFLX",
    "AMD", "COST", "ADBE", "CRM", "ORCL", "CSCO", "INTC", "QCOM", "TXN", "AMAT",
    "LRCX", "MU", "KLAC", "ADI", "PANW", "CRWD", "DDOG", "ZS", "MDB", "SNOW",
    "SHOP", "UBER", "ABNB", "PLTR", "APP", "ARM", "SMCI", "MRVL", "ASML", "CDNS",
    "SNPS", "INTU", "ISRG", "BKNG", "MELI", "VRTX", "REGN", "AMGN", "GILD", "ADP",
    "MAR", "SBUX", "PEP", "LIN", "WMT",
]


@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    entry_date: object
    highest_high: float
    stop: float
    original_shares: float = 0.0
    trimmed: bool = False


def fetch_yahoo_chart(ticker):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = ticker.lower().replace("^", "")
    cache_path = CACHE_DIR / f"{safe}_history.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        "period1": PERIOD1,
        "period2": PERIOD2,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    response = requests.get(url, params=params, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    cache_path.write_text(json.dumps(payload))
    return payload


def load_prices(ticker):
    payload = fetch_yahoo_chart(ticker)
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    if not timestamps:
        raise RuntimeError(f"No data for {ticker}")

    quote = result["indicators"]["quote"][0]
    adjclose = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(timestamps, unit="s").tz_localize("UTC").tz_convert("America/New_York").date,
            "Open": quote["open"],
            "High": quote["high"],
            "Low": quote["low"],
            "Close": quote["close"],
            "AdjClose": adjclose or quote["close"],
            "Volume": quote["volume"],
        }
    ).dropna()

    factor = df["AdjClose"] / df["Close"]
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col] * factor

    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].set_index("Date")
    return add_indicators(df)


def add_indicators(df):
    df = df.copy()
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["VOL20"] = df["Volume"].rolling(20).mean()
    df["RET20"] = df["Close"] / df["Close"].shift(20) - 1
    df["RET63"] = df["Close"] / df["Close"].shift(63) - 1
    df["HIGH20_PREV"] = df["High"].shift(1).rolling(20).max()
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ATR14"] = true_range.rolling(14).mean()
    return df.dropna()


def max_drawdown(values):
    series = pd.Series(values, dtype=float)
    peaks = series.cummax()
    return float((series / peaks - 1).min())


def cagr(final_value, start_date, end_date):
    years = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days / 365.25
    if years <= 0:
        return 0.0
    return final_value ** (1 / years) - 1


def load_universe(tickers):
    data = {}
    errors = []
    for ticker in tickers:
        try:
            data[ticker] = load_prices(ticker)
        except Exception as exc:
            errors.append((ticker, str(exc)))
    qqq = load_prices("QQQ")
    return data, qqq, errors


def common_dates(data, qqq, start):
    return sorted(d for d in qqq.index if d >= pd.Timestamp(start).date())


def signal_for(data, qqq, ticker, date):
    df = data[ticker]
    if date not in df.index or date not in qqq.index:
        return None
    row = df.loc[date]
    qrow = qqq.loc[date]

    market_ok = qrow["Close"] > qrow["SMA200"]
    trend_ok = row["Close"] > row["SMA50"] > row["SMA200"]
    breakout = row["Close"] > row["HIGH20_PREV"]
    volume_ok = row["Volume"] > row["VOL20"] * 1.05
    not_too_extended = row["Close"] < row["SMA50"] * 1.35
    liquid = row["Close"] * row["VOL20"] > 50_000_000
    rs63 = row["RET63"] - qrow["RET63"]

    if not (market_ok and trend_ok and breakout and volume_ok and not_too_extended and liquid and rs63 > 0):
        return None

    score = rs63 * 100 + row["RET20"] * 35 + min(row["Volume"] / row["VOL20"], 3.0) * 2
    initial_stop = max(row["Close"] * 0.92, row["Close"] - 2.0 * row["ATR14"])
    return {
        "ticker": ticker,
        "close": row["Close"],
        "score": score,
        "rs63": rs63,
        "ret20": row["RET20"],
        "vol_ratio": row["Volume"] / row["VOL20"],
        "initial_stop": initial_stop,
        "atr14": row["ATR14"],
    }


def pullback_signal_for(data, qqq, ticker, date):
    df = data[ticker]
    if date not in df.index or date not in qqq.index:
        return None
    row = df.loc[date]
    qrow = qqq.loc[date]

    market_ok = qrow["Close"] > qrow["SMA200"]
    trend_ok = row["Close"] > row["SMA50"] > row["SMA200"]
    liquid = row["Close"] * row["VOL20"] > 50_000_000
    rs63 = row["RET63"] - qrow["RET63"]
    pullback_to_value = row["Close"] < row["SMA20"] * 1.03
    held_support = row["Close"] > row["EMA21"] and row["Low"] <= row["EMA21"] * 1.04
    not_crashing = row["Close"] > row["Close"] / (1 + row["RET20"]) * 0.92 if row["RET20"] > -0.99 else False

    if not (market_ok and trend_ok and liquid and rs63 > 0 and pullback_to_value and held_support and not_crashing):
        return None

    score = rs63 * 100 + row["RET20"] * 25 - abs(row["Close"] / row["EMA21"] - 1) * 20
    initial_stop = max(row["Close"] * 0.90, row["Close"] - 2.0 * row["ATR14"])
    return {
        "ticker": ticker,
        "close": row["Close"],
        "score": score,
        "rs63": rs63,
        "ret20": row["RET20"],
        "initial_stop": initial_stop,
        "atr14": row["ATR14"],
        "ema21": row["EMA21"],
    }


def run_backtest(data, qqq, start="2018-01-01", max_positions=3):
    dates = common_dates(data, qqq, start)
    cash = START_CASH
    positions = {}
    values = []
    trades = []
    queued_buys = []
    queued_sells = set()

    for date in dates:
        # Execute queued sells at today's open.
        for ticker in list(queued_sells):
            if ticker in positions and date in data[ticker].index:
                row = data[ticker].loc[date]
                pos = positions.pop(ticker)
                cash += pos.shares * row["Open"]
                trades.append((date, ticker, "sell", row["Open"], "trend_exit"))
        queued_sells.clear()

        # Execute queued buys at today's open.
        for signal in queued_buys:
            ticker = signal["ticker"]
            if ticker in positions or ticker not in data or date not in data[ticker].index:
                continue
            if len(positions) >= max_positions:
                break
            row = data[ticker].loc[date]
            slots_left = max_positions - len(positions)
            allocation = cash / slots_left
            if allocation <= 0:
                continue
            shares = allocation / row["Open"]
            cash -= allocation
            stop = max(row["Open"] * 0.92, row["Open"] - 2.0 * row["ATR14"])
            positions[ticker] = Position(ticker, shares, row["Open"], date, row["High"], stop)
            trades.append((date, ticker, "buy", row["Open"], "breakout"))
        queued_buys = []

        # Mark to market and process same-day stops.
        for ticker in list(positions):
            row = data[ticker].loc[date]
            pos = positions[ticker]
            pos.highest_high = max(pos.highest_high, row["High"])
            trail_atr = pos.highest_high - 2.5 * row["ATR14"]
            trail_pct = pos.highest_high * 0.88
            pos.stop = max(pos.stop, trail_atr, trail_pct)
            if row["Low"] <= pos.stop:
                cash += pos.shares * pos.stop
                positions.pop(ticker)
                trades.append((date, ticker, "sell", pos.stop, "stop"))

        value = cash
        for ticker, pos in positions.items():
            if date in data[ticker].index:
                value += pos.shares * data[ticker].loc[date]["Close"]
        values.append((date, value))

        # Queue next-day trend exits from today's close.
        if qqq.loc[date]["Close"] < qqq.loc[date]["SMA200"]:
            queued_sells.update(positions.keys())
        else:
            for ticker, pos in positions.items():
                row = data[ticker].loc[date]
                if row["Close"] < row["EMA21"] or row["Close"] < row["SMA50"]:
                    queued_sells.add(ticker)

        # Queue next-day buys from today's close.
        current = set(positions) | queued_sells
        signals = []
        for ticker in data:
            if ticker in current:
                continue
            signal = signal_for(data, qqq, ticker, date)
            if signal:
                signals.append(signal)
        signals.sort(key=lambda x: x["score"], reverse=True)
        queued_buys = signals[: max(0, max_positions - len(positions))]

    final = values[-1][1]
    series = [v for _, v in values]
    start_date = values[0][0]
    end_date = values[-1][0]
    dd = max_drawdown(series)
    annual = cagr(final, start_date, end_date)
    wins = []
    buys = {}
    for date, ticker, side, price, reason in trades:
        if side == "buy":
            buys.setdefault(ticker, []).append(price)
        elif side == "sell" and buys.get(ticker):
            entry = buys[ticker].pop(0)
            wins.append(price / entry - 1)

    return {
        "final": final,
        "cagr": annual,
        "maxdd": dd,
        "calmar": annual / abs(dd) if dd else np.nan,
        "trades": len(trades),
        "round_trips": len(wins),
        "win_rate": float(np.mean([w > 0 for w in wins])) if wins else np.nan,
        "avg_trade": float(np.mean(wins)) if wins else np.nan,
        "values": values,
        "trades_list": trades,
    }


def run_weekly_momentum_rotation(data, qqq, start="2018-01-01", max_positions=3):
    dates = common_dates(data, qqq, start)
    cash = START_CASH
    positions = {}
    values = []
    trades = []
    target_tickers = []
    rebalance_next_open = False

    for idx, date in enumerate(dates):
        qrow = qqq.loc[date]
        market_ok = qrow["Close"] > qrow["SMA200"]

        if rebalance_next_open:
            desired = set(target_tickers if market_ok else [])
            for ticker in list(positions):
                if ticker not in desired and date in data[ticker].index:
                    row = data[ticker].loc[date]
                    pos = positions.pop(ticker)
                    cash += pos.shares * row["Open"]
                    trades.append((date, ticker, "sell", row["Open"], "weekly_rotation"))

            equity = cash
            for ticker, pos in positions.items():
                if date in data[ticker].index:
                    equity += pos.shares * data[ticker].loc[date]["Open"]

            for ticker in target_tickers:
                if not market_ok or ticker in positions or ticker not in data or date not in data[ticker].index:
                    continue
                if len(positions) >= max_positions:
                    break
                row = data[ticker].loc[date]
                slots_left = max_positions - len(positions)
                target_value = equity / max_positions
                allocation = min(cash, target_value if slots_left > 1 else cash)
                if allocation <= 0:
                    continue
                shares = allocation / row["Open"]
                cash -= allocation
                stop = max(row["Open"] * 0.88, row["Open"] - 2.5 * row["ATR14"])
                positions[ticker] = Position(ticker, shares, row["Open"], date, row["High"], stop)
                trades.append((date, ticker, "buy", row["Open"], "weekly_top_momentum"))
            rebalance_next_open = False

        for ticker in list(positions):
            if date not in data[ticker].index:
                continue
            row = data[ticker].loc[date]
            pos = positions[ticker]
            pos.highest_high = max(pos.highest_high, row["High"])
            pos.stop = max(pos.stop, pos.highest_high * 0.85, pos.highest_high - 3.0 * row["ATR14"])
            if row["Low"] <= pos.stop:
                cash += pos.shares * pos.stop
                positions.pop(ticker)
                trades.append((date, ticker, "sell", pos.stop, "stop"))
            elif row["Close"] < row["EMA21"]:
                # Queue-like behavior would be more realistic, but this is a daily close strategy
                # that assumes the alert is acted on near the close.
                cash += pos.shares * row["Close"]
                positions.pop(ticker)
                trades.append((date, ticker, "sell", row["Close"], "ema21_exit"))

        value = cash
        for ticker, pos in positions.items():
            if date in data[ticker].index:
                value += pos.shares * data[ticker].loc[date]["Close"]
        values.append((date, value))

        is_week_end = idx == len(dates) - 1 or pd.Timestamp(dates[idx + 1]).isocalendar().week != pd.Timestamp(date).isocalendar().week
        if is_week_end:
            ranked = []
            if market_ok:
                for ticker, df in data.items():
                    if ticker in positions:
                        continue
                    if date not in df.index:
                        continue
                    row = df.loc[date]
                    if not (row["Close"] > row["SMA50"] > row["SMA200"] and row["RET63"] > qrow["RET63"] and row["Close"] * row["VOL20"] > 50_000_000):
                        continue
                    score = row["RET63"] * 100 + row["RET20"] * 40 + (row["Close"] / row["SMA50"] - 1) * 15
                    ranked.append((score, ticker))
            ranked.sort(reverse=True)
            held = [ticker for ticker in positions if ticker in data and date in data[ticker].index]
            target_tickers = held + [ticker for _, ticker in ranked]
            target_tickers = target_tickers[:max_positions]
            rebalance_next_open = True

    final = values[-1][1]
    series = [v for _, v in values]
    start_date = values[0][0]
    end_date = values[-1][0]
    dd = max_drawdown(series)
    annual = cagr(final, start_date, end_date)
    wins = []
    buys = {}
    for date, ticker, side, price, reason in trades:
        if side == "buy":
            buys.setdefault(ticker, []).append(price)
        elif side == "sell" and buys.get(ticker):
            entry = buys[ticker].pop(0)
            wins.append(price / entry - 1)
    return {
        "final": final,
        "cagr": annual,
        "maxdd": dd,
        "calmar": annual / abs(dd) if dd else np.nan,
        "trades": len(trades),
        "round_trips": len(wins),
        "win_rate": float(np.mean([w > 0 for w in wins])) if wins else np.nan,
        "avg_trade": float(np.mean(wins)) if wins else np.nan,
        "values": values,
        "trades_list": trades,
        "open_positions": positions,
    }


def run_pullback_profit_taker(data, qqq, start="2018-01-01", max_positions=4, profit_target=0.12, trim_fraction=0.50):
    dates = common_dates(data, qqq, start)
    cash = START_CASH
    positions = {}
    values = []
    trades = []
    queued_buys = []
    queued_sells = set()

    for date in dates:
        qrow = qqq.loc[date]
        market_ok = qrow["Close"] > qrow["SMA200"]

        for ticker in list(queued_sells):
            if ticker in positions and date in data[ticker].index:
                row = data[ticker].loc[date]
                pos = positions.pop(ticker)
                cash += pos.shares * row["Open"]
                trades.append((date, ticker, "sell", row["Open"], "trend_exit"))
        queued_sells.clear()

        for signal in queued_buys:
            ticker = signal["ticker"]
            if ticker in positions or ticker not in data or date not in data[ticker].index:
                continue
            if len(positions) >= max_positions:
                break
            row = data[ticker].loc[date]
            slots_left = max_positions - len(positions)
            allocation = cash / slots_left
            if allocation <= 0:
                continue
            shares = allocation / row["Open"]
            cash -= allocation
            stop = max(row["Open"] * 0.90, row["Open"] - 2.0 * row["ATR14"])
            positions[ticker] = Position(ticker, shares, row["Open"], date, row["High"], stop, shares, False)
            trades.append((date, ticker, "buy", row["Open"], "pullback"))
        queued_buys = []

        for ticker in list(positions):
            if date not in data[ticker].index:
                continue
            row = data[ticker].loc[date]
            pos = positions[ticker]
            pos.highest_high = max(pos.highest_high, row["High"])

            if not pos.trimmed and row["High"] >= pos.entry_price * (1 + profit_target):
                trim_price = pos.entry_price * (1 + profit_target)
                sell_shares = pos.shares * trim_fraction
                cash += sell_shares * trim_price
                pos.shares -= sell_shares
                pos.trimmed = True
                pos.stop = max(pos.stop, pos.entry_price)
                trades.append((date, ticker, "trim", trim_price, "profit_target"))

            trail_atr = pos.highest_high - 2.5 * row["ATR14"]
            trail_pct = pos.highest_high * 0.88
            pos.stop = max(pos.stop, trail_atr, trail_pct)
            if row["Low"] <= pos.stop:
                cash += pos.shares * pos.stop
                positions.pop(ticker)
                trades.append((date, ticker, "sell", pos.stop, "runner_stop" if pos.trimmed else "stop"))

        value = cash
        for ticker, pos in positions.items():
            if date in data[ticker].index:
                value += pos.shares * data[ticker].loc[date]["Close"]
        values.append((date, value))

        if not market_ok:
            queued_sells.update(positions.keys())
        else:
            for ticker, pos in positions.items():
                if ticker not in data or date not in data[ticker].index:
                    continue
                row = data[ticker].loc[date]
                if row["Close"] < row["EMA21"] or row["Close"] < row["SMA50"]:
                    queued_sells.add(ticker)

        current = set(positions) | queued_sells
        signals = []
        if market_ok:
            for ticker in data:
                if ticker in current:
                    continue
                signal = pullback_signal_for(data, qqq, ticker, date)
                if signal:
                    signals.append(signal)
        signals.sort(key=lambda x: x["score"], reverse=True)
        queued_buys = signals[: max(0, max_positions - len(positions))]

    final = values[-1][1]
    series = [v for _, v in values]
    start_date = values[0][0]
    end_date = values[-1][0]
    dd = max_drawdown(series)
    annual = cagr(final, start_date, end_date)
    round_trip_returns = []
    lots = {}
    for date, ticker, side, price, reason in trades:
        if side == "buy":
            lots.setdefault(ticker, []).append({"entry": price, "remaining": 1.0, "cash_return": 0.0})
        elif side in {"trim", "sell"} and lots.get(ticker):
            lot = lots[ticker][0]
            if side == "trim":
                fraction = trim_fraction * lot["remaining"]
                lot["cash_return"] += fraction * (price / lot["entry"])
                lot["remaining"] -= fraction
            else:
                lot["cash_return"] += lot["remaining"] * (price / lot["entry"])
                round_trip_returns.append(lot["cash_return"] - 1)
                lots[ticker].pop(0)

    return {
        "final": final,
        "cagr": annual,
        "maxdd": dd,
        "calmar": annual / abs(dd) if dd else np.nan,
        "trades": len(trades),
        "round_trips": len(round_trip_returns),
        "win_rate": float(np.mean([w > 0 for w in round_trip_returns])) if round_trip_returns else np.nan,
        "avg_trade": float(np.mean(round_trip_returns)) if round_trip_returns else np.nan,
        "values": values,
        "trades_list": trades,
        "open_positions": positions,
    }


def scan_today(data, qqq, asof=None, limit=15):
    if asof is None:
        asof = max(qqq.index)
    signals = [signal_for(data, qqq, ticker, asof) for ticker in data]
    signals = [s for s in signals if s]
    signals.sort(key=lambda x: x["score"], reverse=True)
    return asof, signals[:limit]


def scan_weekly_rotation(data, qqq, asof=None, limit=10):
    if asof is None:
        asof = max(qqq.index)
    qrow = qqq.loc[asof]
    ranked = []
    if qrow["Close"] > qrow["SMA200"]:
        for ticker, df in data.items():
            if asof not in df.index:
                continue
            row = df.loc[asof]
            if not (row["Close"] > row["SMA50"] > row["SMA200"] and row["RET63"] > qrow["RET63"] and row["Close"] * row["VOL20"] > 50_000_000):
                continue
            score = row["RET63"] * 100 + row["RET20"] * 40 + (row["Close"] / row["SMA50"] - 1) * 15
            stop = max(row["Close"] * 0.88, row["Close"] - 2.5 * row["ATR14"])
            ranked.append(
                {
                    "ticker": ticker,
                    "score": score,
                    "close": row["Close"],
                    "initial_stop": stop,
                    "ret63": row["RET63"],
                    "ret20": row["RET20"],
                    "sma50": row["SMA50"],
                    "sma200": row["SMA200"],
                }
            )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return asof, ranked[:limit]


def scan_pullback_profit_taker(data, qqq, asof=None, limit=10):
    if asof is None:
        asof = max(qqq.index)
    signals = [pullback_signal_for(data, qqq, ticker, asof) for ticker in data]
    signals = [s for s in signals if s]
    signals.sort(key=lambda x: x["score"], reverse=True)
    return asof, signals[:limit]


def print_result(label, result):
    print(
        f"{label}: final={result['final']:.1f}x "
        f"cagr={result['cagr']:.1%} maxdd={result['maxdd']:.1%} "
        f"calmar={result['calmar']:.2f} trades={result['trades']} "
        f"round_trips={result['round_trips']} win_rate={result['win_rate']:.1%} "
        f"avg_trade={result['avg_trade']:.1%}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--max-positions", type=int, default=3)
    args = parser.parse_args()

    data, qqq, errors = load_universe(UNIVERSE)
    result = run_backtest(data, qqq, args.start, args.max_positions)
    rotation = run_weekly_momentum_rotation(data, qqq, args.start, args.max_positions)
    profit_taker = run_pullback_profit_taker(data, qqq, args.start, 4, 0.12, 0.50)
    train = run_weekly_momentum_rotation(data, qqq, "2018-01-01", args.max_positions)
    test = run_weekly_momentum_rotation(data, qqq, "2021-01-01", args.max_positions)
    profit_test = run_pullback_profit_taker(data, qqq, "2021-01-01", 4, 0.12, 0.50)
    asof, signals = scan_today(data, qqq)
    rotation_asof, rotation_signals = scan_weekly_rotation(data, qqq)
    profit_asof, profit_signals = scan_pullback_profit_taker(data, qqq)

    print("Swing breakout strategy")
    print(f"Loaded stocks: {len(data)} | data errors: {errors}")
    print_result(f"Backtest from {args.start}", result)
    print("\nWeekly swing momentum rotation")
    print_result(f"Backtest from {args.start}", rotation)
    print_result("Robustness from 2018", train)
    print_result("Out-of-sample style from 2021", test)

    print("\nPullback profit-taking swing strategy")
    print_result(f"Backtest from {args.start}", profit_taker)
    print_result("Out-of-sample style from 2021", profit_test)
    print(f"\nCurrent scan as of {asof}:")
    if not signals:
        print("No fresh buy signals.")
    else:
        print("ticker score close initial_stop rs63 ret20 vol_ratio")
        for s in signals:
            print(
                f"{s['ticker']:>5} {s['score']:>6.2f} {s['close']:>8.2f} "
                f"{s['initial_stop']:>11.2f} {s['rs63']:>6.1%} "
                f"{s['ret20']:>6.1%} {s['vol_ratio']:>8.2f}"
            )

    print(f"\nWeekly rotation buy list as of {rotation_asof}:")
    if not rotation_signals:
        print("No rotation candidates; market filter or stock filters are off.")
    else:
        print("ticker score close initial_stop ret63 ret20 sma50 sma200")
        for s in rotation_signals[: args.max_positions]:
            print(
                f"{s['ticker']:>5} {s['score']:>6.2f} {s['close']:>8.2f} "
                f"{s['initial_stop']:>11.2f} {s['ret63']:>6.1%} "
                f"{s['ret20']:>6.1%} {s['sma50']:>8.2f} {s['sma200']:>8.2f}"
            )

    print(f"\nPullback profit-taking buy list as of {profit_asof}:")
    if not profit_signals:
        print("No pullback buy signals.")
    else:
        print("ticker score close initial_stop rs63 ret20 ema21")
        for s in profit_signals[:4]:
            print(
                f"{s['ticker']:>5} {s['score']:>6.2f} {s['close']:>8.2f} "
                f"{s['initial_stop']:>11.2f} {s['rs63']:>6.1%} "
                f"{s['ret20']:>6.1%} {s['ema21']:>8.2f}"
            )

    out_dir = Path("research/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(result["values"], columns=["Date", "Value"]).to_csv(out_dir / "swing_equity_curve.csv", index=False)
    pd.DataFrame(result["trades_list"], columns=["Date", "Ticker", "Side", "Price", "Reason"]).to_csv(
        out_dir / "swing_trades.csv", index=False
    )
    pd.DataFrame(rotation["values"], columns=["Date", "Value"]).to_csv(out_dir / "weekly_rotation_equity_curve.csv", index=False)
    pd.DataFrame(rotation["trades_list"], columns=["Date", "Ticker", "Side", "Price", "Reason"]).to_csv(
        out_dir / "weekly_rotation_trades.csv", index=False
    )
    pd.DataFrame(profit_taker["values"], columns=["Date", "Value"]).to_csv(
        out_dir / "pullback_profit_taker_equity_curve.csv", index=False
    )
    pd.DataFrame(profit_taker["trades_list"], columns=["Date", "Ticker", "Side", "Price", "Reason"]).to_csv(
        out_dir / "pullback_profit_taker_trades.csv", index=False
    )
    pd.DataFrame(signals).to_csv(out_dir / "swing_current_signals.csv", index=False)
    pd.DataFrame(rotation_signals).to_csv(out_dir / "weekly_rotation_current_signals.csv", index=False)
    pd.DataFrame(profit_signals).to_csv(out_dir / "pullback_profit_taker_current_signals.csv", index=False)
    print("\nWrote research/out/swing_equity_curve.csv")
    print("Wrote research/out/swing_trades.csv")
    print("Wrote research/out/swing_current_signals.csv")
    print("Wrote research/out/weekly_rotation_equity_curve.csv")
    print("Wrote research/out/weekly_rotation_trades.csv")
    print("Wrote research/out/weekly_rotation_current_signals.csv")
    print("Wrote research/out/pullback_profit_taker_equity_curve.csv")
    print("Wrote research/out/pullback_profit_taker_trades.csv")
    print("Wrote research/out/pullback_profit_taker_current_signals.csv")


if __name__ == "__main__":
    main()
