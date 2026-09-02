#!/usr/bin/env python3
"""Replay the SAME strategy.evaluate() over history.

  py backtest.py --symbol EURUSD --timeframe M15 --bars 2000
  py backtest.py --csv data/eurusd.csv         # offline: ts,open,high,low,close

Fill model, deliberately pessimistic:
  - entry at the NEXT bar's open after the signal bar closes
  - if a bar touches both stop and target, the STOP is assumed hit first
  - no spread/commission modelled, so real results will be worse
A backtest is a check that the logic does what you think, not a forecast.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import strategy  # noqa: E402
import strategy_trend  # noqa: E402
import strategy_mtf  # noqa: E402
import strategy_qt
import strategy_session  # noqa: E402

FAMILIES = {"smc": strategy, "trend": strategy_trend, "mtf": strategy_mtf, "session": strategy_session, "qt": strategy_qt}


def module_for(params: dict):
    return FAMILIES.get(params.get("family", "smc"), strategy)
from broker_mt5 import Candle  # noqa: E402


def load_csv(path: str) -> list[Candle]:
    out = []
    with open(path) as fh:
        for row in csv.DictReader(fh):
            out.append(
                Candle(
                    ts=row["ts"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                )
            )
    return out


def run(candles: list[Candle], params: dict, verbose: bool = False) -> dict:
    trades = []
    open_trade = None
    ambiguous = 0
    mod = module_for(params)
    ctx = mod.Context(candles, params)   # built once, not per bar

    for i in range(len(candles) - 1):
        bar = candles[i]

        if open_trade:
            t = open_trade
            # ORDER MATTERS. Test this bar against the stop that was already
            # standing when the bar opened, and only THEN ratchet the trail
            # using this bar's close.
            #
            # Doing it the other way round tightens the stop with end-of-bar
            # information and then asks whether the bar's low reached it — so
            # a bar that dipped and recovered books an exit at the new, better
            # price that was never actually available. That fiction scored
            # +0.058R per trade on a driftless random walk, which is how it
            # was caught.
            hit_stop = bar.low <= t["stop"] if t["dir"] == "BUY" else bar.high >= t["stop"]
            hit_tgt = bar.high >= t["target"] if t["dir"] == "BUY" else bar.low <= t["target"]
            exit_px = exit_kind = None
            both = hit_stop and hit_tgt
            if both:
                ambiguous += 1
            # When ONE bar touches both levels, the order is unknowable from
            # OHLC alone. Default is the pessimistic assumption (stop first).
            # "target" gives the optimistic bound; the truth is in between.
            if both and params.get("tie_break", "stop") == "target":
                hit_stop = False
            if hit_stop:
                # GAP HANDLING. If the bar opened beyond the stop, the market
                # jumped over it — a real stop order fills at the OPEN, not at
                # the stop price. Filling at the stop books a price that never
                # traded, and it is a systematic gift: it truncates every gap
                # loss and inflates every gap win.
                #
                # Left unhandled this manufactured +0.043 in price terms per
                # trade on a pure martingale, at 8.5 sigma.
                if t["dir"] == "BUY":
                    exit_px = min(t["stop"], bar.open)
                else:
                    exit_px = max(t["stop"], bar.open)
                exit_kind = "stop" if exit_px == t["stop"] else "gap"
            elif hit_tgt:
                # A gap through the target fills better, not worse.
                if t["dir"] == "BUY":
                    exit_px = max(t["target"], bar.open)
                else:
                    exit_px = min(t["target"], bar.open)
                exit_kind = "target" if exit_px == t["target"] else "gap"
            if exit_px is not None:
                r_unit = t["risk"]
                # Exiting crosses the spread the other way.
                exit_px = (exit_px - t["half"]) if t["dir"] == "BUY" else (exit_px + t["half"])
                pnl = (exit_px - t["entry"]) if t["dir"] == "BUY" else (t["entry"] - exit_px)
                t.update(exit=exit_px, exit_kind=exit_kind, exit_ts=bar.ts,
                         r=pnl / r_unit if r_unit else 0.0)
                trades.append(t)
                open_trade = None
            else:
                if t.get("trail"):
                    a = ctx.atr[i]
                    if a:
                        if t["dir"] == "BUY":
                            t["stop"] = max(t["stop"], bar.close - t["trail"] * a)
                        else:
                            t["stop"] = min(t["stop"], bar.close + t["trail"] * a)
                continue

        if open_trade:
            continue

        sig = mod.evaluate_at(candles, params, ctx, i)
        if sig is None:
            continue
        if params.get("reverse"):
            # Take the opposite side of every signal. Note this does NOT flip
            # the sign of the result: costs are paid either way, so a system
            # losing X does not become a system winning X when reversed.
            sig.direction = "SELL" if sig.direction == "BUY" else "BUY"
        entry = candles[i + 1].open
        # Transaction cost, in price terms, applied at ENTRY and again at EXIT.
        # Buying lifts the ask, selling hits the bid; the round trip costs one
        # full spread. Every number this project has produced so far assumed
        # zero, which flatters every result by roughly 0.04-0.06R at M15.
        half = float(params.get("spread_price", 0.0)) / 2.0
        # Re-anchor stop/target to the actual entry so R stays honest.
        dist = abs(sig.entry - sig.stop)
        rr = abs(sig.target - sig.entry) / dist if dist else 2.0
        if sig.direction == "BUY":
            entry += half                    # filled at the ask
            stop, target = entry - dist, entry + rr * dist
        else:
            entry -= half                    # filled at the bid
            stop, target = entry + dist, entry - rr * dist
        open_trade = {
            "dir": sig.direction, "entry": entry, "stop": stop, "target": target,
            "risk": abs(entry - stop),          # fixed at entry; a trailing
                                                 # stop must not rescale R
            "trail": getattr(sig, "trail_atr", None),
            "half": half,
            "entry_ts": candles[i + 1].ts, "reason": sig.reason,
        }

    wins = [t for t in trades if t["r"] > 0]
    total_r = sum(t["r"] for t in trades)
    # Second moment, so callers can put an error bar on expectancy. For a
    # trailing-stop system there is no fixed R multiple, so "win rate vs
    # breakeven" is meaningless — mean R with a standard error is the only
    # honest summary.
    n_t = len(trades)
    r_mean = total_r / n_t if n_t else 0.0
    r_var = (sum((t["r"] - r_mean) ** 2 for t in trades) / (n_t - 1)) if n_t > 1 else 0.0

    peak = eq = 0.0
    max_dd = 0.0
    for t in trades:
        eq += t["r"]
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    if verbose:
        for t in trades:
            print(f"  {t['entry_ts']}  {t['dir']:<4} entry {t['entry']:.5f} "
                  f"-> {t['exit_kind']:<6} {t['r']:+.2f}R")

    return {
        "bars": len(candles),
        "trades": len(trades),
        "wins": len(wins),
        "win_rate": round(100 * len(wins) / len(trades), 1) if trades else 0.0,
        "total_R": round(total_r, 2),
        "avg_R": round(total_r / len(trades), 3) if trades else 0.0,
        "max_drawdown_R": round(max_dd, 2),
        "still_open": bool(open_trade),
        "r_mean": round(r_mean, 4),
        "r_var": r_var,
        "gap_exits": len([t for t in trades if t.get("exit_kind") == "gap"]),
        "ambiguous_bars": ambiguous,
        # Einzeltrades mitgeben, damit Aufrufer eigene Regeln (Kostengrenze,
        # Korrelationsgruppen, Margin) darauf anwenden koennen.
        "trades_list": trades,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--symbol")
    ap.add_argument("--timeframe", default="M15")
    ap.add_argument("--bars", type=int, default=2000)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    with open(os.path.join(HERE, "config.json")) as fh:
        cfg = json.load(fh)

    if args.csv:
        candles = load_csv(args.csv)
        label = args.csv
    elif args.symbol:
        from scan import connect, load_env
        load_env()
        client = connect()
        candles = client.candles(args.symbol, args.timeframe, args.bars)
        client.close()
        label = f"{args.symbol} {args.timeframe}"
    else:
        ap.error("need --csv or --symbol")

    print(f"\nBacktest: {label}")
    stats = run(candles, cfg["strategy_params"], verbose=args.verbose)
    for k, v in stats.items():
        print(f"  {k:<16} {v}")
    print("\nR = multiples of the risked amount. Costs are not modelled.\n")


if __name__ == "__main__":
    main()
