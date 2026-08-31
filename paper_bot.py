#!/usr/bin/env python3
"""PAPER BOT — no broker at all.

Data from public feeds (Binance for crypto, Yahoo for FX and indices), setups
evaluated with the same pre-registered candidates, and every open position
mirrored into the TERMINAL's portfolio view (F7).

Nothing to install, no account, no ID, no MetaTrader. The virtual book lives
in paper_book.json next to this file; the terminal is a mirror of it, not the
source of truth, so closing the terminal loses nothing.

HONEST ABOUT WHAT THIS IS
  Fills are simulated at the signal bar's close, with a spread charged both
  ways from datafeed.PAPER_SPREAD_FRAC. That is weaker evidence than a real
  broker fill — no slippage, no requotes, no widening around news. It is
  still a clean forward sample, which is the thing we actually lacked.

  py paper_bot.py            one pass — schedule this
  py paper_bot.py --report   how the candidates are doing
  py paper_bot.py --reset    wipe the book and start over
"""
from __future__ import annotations

import argparse, json, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BOOK = os.path.join(HERE, "paper_book.json")
LOG = os.path.join(HERE, "paper_log.jsonl")

START_EQUITY = 100_000.0
RISK_PCT = 0.5              # of equity, per position
MAX_OPEN = 15
MAX_PER_CANDIDATE = 4
MAX_NEW_PER_SCAN = 5
# At most this many open positions per correlation group (see datafeed.groups).
# 1 means: never two bets on the same underlying story at the same time.
MAX_PER_GROUP = 1
# Nach einem Schliessen von Hand bleibt das Symbol so lange gesperrt. Ohne das
# oeffnet der naechste Scan denselben Trade wieder, weil die Einstiegsbedingung
# ueber viele Balken hinweg gueltig bleibt - das Schliessen waere wirkungslos.
MANUAL_COOLDOWN_MIN = 720


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_book() -> dict:
    if os.path.exists(BOOK):
        try:
            with open(BOOK) as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"equity": START_EQUITY, "open": [], "closed": []}


def save_book(b: dict) -> None:
    tmp = BOOK + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(b, fh, indent=2)
    os.replace(tmp, BOOK)


def log(rec: dict) -> None:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


# ---------------------------------------------------------------- terminal --
TERMINAL = "http://127.0.0.1:8765"
PREFIX = "bot-"


def term_post(path: str, body: dict):
    import urllib.request
    req = urllib.request.Request(TERMINAL + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def term_up() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(TERMINAL + "/api/portfolio", timeout=5):
            return True
    except Exception:
        return False


def push_terminal(book: dict) -> None:
    """Mirror the open book into the terminal. Quantity is signed so the
    terminal's own value-minus-cost arithmetic gets shorts right."""
    import datafeed
    if not term_up():
        return
    try:
        import urllib.request
        with urllib.request.urlopen(TERMINAL + "/api/portfolio", timeout=8) as r:
            pf = json.loads(r.read().decode())
        have = {p["id"] for p in pf.get("positions", [])
                if str(p.get("id", "")).startswith(PREFIX)}
    except Exception:
        have = set()

    want = set()
    for p in book["open"]:
        pid = PREFIX + p["id"]
        want.add(pid)
        sym = datafeed.TERMINAL_SYMBOL.get(p["symbol"], p["symbol"])
        qty = p["qty"] * (1 if p["direction"] == "BUY" else -1)
        try:
            term_post("/api/position", {
                "action": "add", "id": pid, "symbol": sym,
                "qty": round(qty, 6), "cost": round(p["entry"], 6),
                "note": f"{p['cand']} | {p['symbol']} {p['direction']} | "
                        f"SL {p['stop']} TP {p['target']} | opened {p['opened'][:16]}",
                "date": p["opened"][:10]})
        except Exception:
            pass
    for pid in have - want:
        try:
            term_post("/api/position", {"action": "delete", "id": pid})
        except Exception:
            pass


# -------------------------------------------------------------------- scan --
def run_once(verbose: bool = True) -> None:
    import backtest, datafeed
    from forward import CANDIDATES

    book = load_book()
    open_by_cand: dict[str, int] = {}
    for p in book["open"]:
        open_by_cand[p["cand"]] = open_by_cand.get(p["cand"], 0) + 1

    opened = closed = 0
    seen = {(p["cand"], p["symbol"], p["signal_bar"]) for p in book["open"]}
    seen |= {(p["cand"], p["symbol"], p["signal_bar"]) for p in book["closed"]}

    # Fair ordering: rotate which candidate gets first refusal on a symbol,
    # so no candidate is favoured just for being first in the list.
    turn = int(book.get("scan_turn") or 0)
    rotated = CANDIDATES[turn % len(CANDIDATES):] + CANDIDATES[:turn % len(CANDIDATES)]
    book["scan_turn"] = (turn + 1) % len(CANDIDATES)

    # One batched Yahoo request for all 40 Yahoo symbols, instead of 40.
    try:
        got = datafeed.prefetch(datafeed.ALL_SYMBOLS, "M15", 900)
        if verbose:
            print(f"  prefetch: {len(got)} symbols cached")
    except Exception as exc:
        if verbose:
            print(f"  prefetch failed, falling back per-symbol: {str(exc)[:60]}")

    for sym in datafeed.ALL_SYMBOLS:
        try:
            cs = datafeed.fetch(sym, "M15", 900)
        except Exception as exc:
            if verbose:
                print(f"  {sym}: feed error {str(exc)[:50]}")
            continue
        if len(cs) < 320:
            continue
        bars = cs[:-1]                       # drop the forming bar
        last = bars[-1]

        # ---- resolve open positions against the bars since entry ----
        still = []
        for p in book["open"]:
            if p["symbol"] != sym:
                still.append(p); continue
            after = [c for c in bars if c.ts > p["entry_bar"]]
            res = px = None
            for c in after:
                if p["direction"] == "BUY":
                    if c.low <= p["stop"]:  res, px = "stop", p["stop"]; break
                    if c.high >= p["target"]: res, px = "target", p["target"]; break
                else:
                    if c.high >= p["stop"]: res, px = "stop", p["stop"]; break
                    if c.low <= p["target"]: res, px = "target", p["target"]; break
            if res is None:
                still.append(p); continue
            half = datafeed.paper_spread(sym, px) / 2
            exit_px = px - half if p["direction"] == "BUY" else px + half
            pnl_price = (exit_px - p["entry"]) if p["direction"] == "BUY" \
                        else (p["entry"] - exit_px)
            pnl = pnl_price * p["qty"]
            r = pnl / p["risk_amount"] if p["risk_amount"] else 0.0
            p.update(closed_at=now_iso(), outcome=res, exit=round(exit_px, 6),
                     pnl=round(pnl, 2), r=round(r, 3))
            book["closed"].append(p)
            book["equity"] = round(book["equity"] + pnl, 2)
            open_by_cand[p["cand"]] = max(open_by_cand.get(p["cand"], 1) - 1, 0)
            log({"kind": "CLOSE", "ts": now_iso(), **p})
            closed += 1
        book["open"] = still

        # ---- look for new setups ----
        for cid, _tf, params, _why in rotated:
            if opened >= MAX_NEW_PER_SCAN: break
            if len(book["open"]) >= MAX_OPEN: break
            if open_by_cand.get(cid, 0) >= MAX_PER_CANDIDATE: continue
            # One position per symbol, across ALL candidates. Two candidates
            # holding the same coin long and short at once is not a hedge —
            # it is two spreads paid for zero net exposure. Same-direction
            # doubling is just undisclosed double risk on one asset.
            busy = next((p for p in book["open"] if p["symbol"] == sym), None)
            if busy is not None:
                if busy["cand"] != cid:
                    log({"kind": "SKIP_SYMBOL_BUSY", "ts": now_iso(),
                         "cand": cid, "symbol": sym,
                         "held_by": busy["cand"], "held_dir": busy["direction"]})
                continue

            # And only one bet per correlation group: SOL and DOGE together are
            # one crypto position in two tickets, not two independent trades.
            # Von Hand geschlossen? Dann ist das eine Entscheidung, keine
            # Marktlage - Symbol vorerst in Ruhe lassen.
            blocked_until = None
            for c in book.get("closed") or []:
                if c.get("symbol") != sym or c.get("outcome") != "manual":
                    continue
                try:
                    t = datetime.fromisoformat(c.get("closed_at"))
                except Exception:
                    continue
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                age_min = (datetime.now(timezone.utc) - t).total_seconds() / 60.0
                if age_min < MANUAL_COOLDOWN_MIN:
                    left = MANUAL_COOLDOWN_MIN - age_min
                    if blocked_until is None or left > blocked_until:
                        blocked_until = left
            if blocked_until is not None:
                log({"kind": "SKIP_MANUAL_COOLDOWN", "ts": now_iso(),
                     "cand": cid, "symbol": sym,
                     "minutes_left": round(blocked_until, 1)})
                continue

            grp = datafeed.group_of(sym)
            held = [p for p in book["open"]
                    if datafeed.group_of(p["symbol"]) == grp]
            if len(held) >= MAX_PER_GROUP:
                log({"kind": "SKIP_GROUP_FULL", "ts": now_iso(),
                     "cand": cid, "symbol": sym, "group": grp,
                     "held": [{"symbol": p["symbol"], "cand": p["cand"],
                               "dir": p["direction"]} for p in held]})
                continue
            p = dict(params); p["utc_offset"] = 0      # public feeds are UTC
            mod = backtest.module_for(p)
            try:
                ctx = mod.Context(bars, p)
                sig = mod.evaluate_at(bars, p, ctx, len(bars) - 1)
            except Exception:
                continue
            if sig is None: continue
            if (cid, sym, sig.signal_bar) in seen: continue

            half = datafeed.paper_spread(sym, sig.entry) / 2
            entry = sig.entry + (half if sig.direction == "BUY" else -half)
            dist = abs(entry - sig.stop)
            if dist <= 0: continue
            risk_amount = book["equity"] * RISK_PCT / 100.0
            qty = risk_amount / dist
            rec = {"id": f"{int(datetime.now(timezone.utc).timestamp()*1000)}"
                         f"-{cid}-{sym}",
                   "cand": cid, "symbol": sym,
                   # the terminal prices open positions from this
                   "yahoo": datafeed.TERMINAL_SYMBOL.get(sym, sym),
                   "direction": sig.direction,
                   "entry": round(entry, 6), "stop": round(sig.stop, 6),
                   "target": round(sig.target, 6), "qty": round(qty, 6),
                   "risk_amount": round(risk_amount, 2),
                   # stored so the terminal can charge the same cost when you
                   # close a position by hand
                   "spread_frac": datafeed.PAPER_SPREAD_FRAC.get(sym, 0.0002),
                   "signal_bar": sig.signal_bar, "entry_bar": last.ts,
                   "opened": now_iso(), "reason": sig.reason}
            book["open"].append(rec)
            seen.add((cid, sym, sig.signal_bar))
            open_by_cand[cid] = open_by_cand.get(cid, 0) + 1
            log({"kind": "OPEN", "ts": now_iso(), **rec})
            opened += 1
            if verbose:
                print(f"  OPEN  {sym:<8}{sig.direction:<5}{cid:<18}"
                      f"@ {entry:.5f} SL {sig.stop:.5f} TP {sig.target:.5f}")

    save_book(book)
    push_terminal(book)
    log({"kind": "SCAN", "ts": now_iso(), "opened": opened, "closed": closed,
         "open_total": len(book["open"]), "equity": book["equity"]})
    if verbose:
        print(f"[{now_iso()}] {opened} opened, {closed} closed, "
              f"{len(book['open'])} open, equity {book['equity']:,.2f}"
              + ("  (terminal synced)" if term_up() else "  (terminal closed)"))


def report() -> None:
    book = load_book()
    cl = book["closed"]
    print(f"\nPAPER BOOK   equity {book['equity']:,.2f}  "
          f"({book['equity']-START_EQUITY:+,.2f} from {START_EQUITY:,.0f})")
    print(f"{len(book['open'])} open, {len(cl)} closed\n")
    if book["open"]:
        print(f"{'symbol':<9}{'side':<5}{'cand':<18}{'entry':>11}{'stop':>11}{'target':>11}")
        print("-" * 66)
        for p in book["open"]:
            print(f"{p['symbol']:<9}{p['direction']:<5}{p['cand']:<18}"
                  f"{p['entry']:>11.5f}{p['stop']:>11.5f}{p['target']:>11.5f}")
        print()
    if not cl:
        print("No closed trades yet.\n"); return
    from forward import CANDIDATES
    print(f"{'candidate':<18}{'closed':>8}{'wins':>7}{'win%':>7}{'meanR':>9}{'P&L':>12}")
    print("-" * 62)
    for cid, _t, _p, _w in CANDIDATES:
        rs = [c["r"] for c in cl if c["cand"] == cid]
        pl = sum(c["pnl"] for c in cl if c["cand"] == cid)
        if not rs:
            print(f"{cid:<18}{0:>8}       -      -        -           -"); continue
        w = len([x for x in rs if x > 0])
        print(f"{cid:<18}{len(rs):>8}{w:>7}{100*w/len(rs):>7.1f}"
              f"{sum(rs)/len(rs):>9.3f}{pl:>12,.2f}")
    print("-" * 62)
    allr = [c["r"] for c in cl]
    m = sum(allr)/len(allr)
    if len(allr) > 1:
        sd = (sum((x-m)**2 for x in allr)/(len(allr)-1))**0.5
        se = sd/len(allr)**0.5
        print(f"\npooled {m:+.3f}R   95% CI {m-1.96*se:+.3f} .. {m+1.96*se:+.3f}")
    ctrl = [c["r"] for c in cl if c["cand"] == "sess_nowindow"]
    timed = [c["r"] for c in cl if c["cand"].startswith("sess_") and
             c["cand"] != "sess_nowindow"]
    if ctrl and timed:
        print(f"timed sessions {sum(timed)/len(timed):+.3f}R  vs  "
              f"control (any hour) {sum(ctrl)/len(ctrl):+.3f}R")
    if len(cl) < 100:
        print(f"\n{len(cl)} closed. Not readable below ~100; ~300 to separate a "
              f"small edge from noise.")
    print()


# Ein Pausenschalter, der ohne Administratorrechte auskommt: liegt die Datei
# PAUSED neben diesem Skript, beendet sich jeder Scan sofort. Die geplante
# Aufgabe darf weiter feuern, sie tut dann nur nichts.
PAUSE_FILE = os.path.join(HERE, "PAUSED")


def paused() -> bool:
    return os.path.exists(PAUSE_FILE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    try:
        if a.reset:
            if os.path.exists(BOOK): os.remove(BOOK)
            print("book wiped; terminal entries will clear on the next scan")
        elif a.report:
            report()
        elif paused():
            print("PAUSED-Datei vorhanden - dieser Scan tut nichts. "
                  "Zum Fortsetzen die Datei loeschen.")
        else:
            run_once()
    except Exception as exc:
        import traceback; traceback.print_exc()
        with open(os.path.join(HERE, "crash.log"), "a") as fh:
            fh.write(f"\n=== {now_iso()} paper_bot ===\n{traceback.format_exc()}")
