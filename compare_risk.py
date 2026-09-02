"""Vergleich: altes Risikomodell gegen neues, auf DEINEN echten Trades.

  ALT:  0,5% Risiko pro Trade, keine Kapitalpruefung
  NEU:  1,0% Risiko, begrenzt durch freie Margin (Position wird verkleinert)

Wichtig vorweg: R aendert sich durch die Positionsgroesse NICHT. R ist der
Gewinn gemessen am eigenen Risiko; wer doppelt so gross handelt, gewinnt und
verliert doppelt. Was sich aendert, sind zwei Dinge:

  1. der Euro-Betrag skaliert
  2. Trades mit sehr engem Stop werden verkleinert und wiegen dadurch weniger

Punkt 2 ist der einzige, der die Rendite echt veraendern kann - und zwar
gerade dann, wenn enge Stops schlechter laufen als weite. Genau das prueft
dieses Skript.

  python compare_risk.py                 Buch automatisch finden
  python compare_risk.py --book PFAD     bestimmte Datei
  python compare_risk.py --url ADRESSE   vom Handy holen
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import datafeed  # noqa: E402

START = 100_000.0
OLD_RISK_PCT = 0.5
NEW_RISK_PCT = 1.0
MIN_SIZE_FRAC = 0.10


def load_book(path=None, url=None):
    if url:
        req = urllib.request.Request(url, headers={"User-Agent": "compare"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()), url
    for p in [path,
              os.path.join(HERE, "paper_book.json"),
              os.path.join(os.path.dirname(HERE), "paper_book.json")]:
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f), p
    # letzte Chance: die Adresse aus paper_source.txt
    src = os.path.join(HERE, "paper_source.txt")
    if os.path.exists(src):
        for line in open(src, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                return load_book(url=line)
    raise SystemExit("Kein paper_book.json gefunden. Mit --book oder --url angeben.")


def simulate(closed, risk_pct, cap_margin):
    """Konto durch alle abgeschlossenen Trades laufen lassen."""
    eq = START
    rows, capped, skipped = [], 0, 0
    for c in closed:
        r = c.get("r")
        entry = float(c.get("entry") or 0)
        stop = float(c.get("stop") or 0)
        sym = c.get("symbol", "")
        if r is None or not entry or not stop:
            continue
        dist = abs(entry - stop)
        if dist <= 0:
            continue
        want_risk = eq * risk_pct / 100.0
        qty = want_risk / dist
        risk = want_risk
        if cap_margin:
            lev = datafeed.leverage_of(sym)
            need = qty * entry / max(1, lev)
            # vereinfachend: eine Position zur Zeit, also ist alles frei
            if need > eq:
                afford = eq * lev / entry
                if afford < qty * MIN_SIZE_FRAC:
                    skipped += 1
                    continue
                qty = afford
                risk = qty * dist
                capped += 1
        pnl = float(r) * risk
        eq += pnl
        rows.append({"symbol": sym, "r": float(r), "risk": risk, "pnl": pnl,
                     "stop_pct": dist / entry * 100})
    return eq, rows, capped, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book")
    ap.add_argument("--url")
    a = ap.parse_args()
    book, src = load_book(a.book, a.url)
    closed = [c for c in (book.get("closed") or []) if c.get("r") is not None]
    print(f"\nQuelle: {src}")
    print(f"Abgeschlossene Trades: {len(closed)}")
    if not closed:
        raise SystemExit("Keine abgeschlossenen Trades im Buch - nichts zu vergleichen.")

    rs = [float(c["r"]) for c in closed]
    wins = sum(1 for r in rs if r > 0)
    print(f"Trefferquote: {wins/len(rs)*100:.1f}%   Summe R: {sum(rs):+.2f}   "
          f"R pro Trade: {sum(rs)/len(rs):+.4f}")

    print("\n" + "=" * 68)
    print("VERGLEICH")
    print("=" * 68)
    print(f"{'Modell':<34}{'Endkapital':>14}{'Ergebnis':>12}{'Rendite':>8}")
    print("-" * 68)
    eq_old, rows_old, _, _ = simulate(closed, OLD_RISK_PCT, False)
    eq_new, rows_new, capped, skipped = simulate(closed, NEW_RISK_PCT, True)
    for name, eq in [(f"ALT  {OLD_RISK_PCT}% ohne Kapitalpruefung", eq_old),
                     (f"NEU  {NEW_RISK_PCT}% mit Margin-Grenze", eq_new)]:
        print(f"{name:<34}{eq:>14,.2f}{eq-START:>+12,.2f}{(eq/START-1)*100:>7.2f}%")
    print("-" * 68)
    print(f"{'davon verkleinert':<34}{capped:>14}")
    print(f"{'davon uebersprungen (zu klein)':<34}{skipped:>14}")

    # Der eigentliche Punkt: haengt das Ergebnis vom Stop-Abstand ab?
    print("\n" + "=" * 68)
    print("LAUFEN ENGE STOPS SCHLECHTER? (das entscheidet, ob die Grenze hilft)")
    print("=" * 68)
    buckets = [(0, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 99)]
    print(f"{'Stop-Abstand':<16}{'Trades':>8}{'Treffer':>10}{'R pro Trade':>14}{'Summe R':>10}")
    print("-" * 68)
    for lo, hi in buckets:
        sel = [x for x in rows_old if lo <= x["stop_pct"] < hi]
        if not sel:
            print(f"{f'{lo}-{hi}%':<16}{0:>8}{'-':>10}{'-':>14}{'-':>10}")
            continue
        rr = [x["r"] for x in sel]
        w = sum(1 for r in rr if r > 0) / len(rr) * 100
        print(f"{f'{lo}-{hi}%':<16}{len(sel):>8}{w:>9.1f}%{sum(rr)/len(rr):>+14.4f}{sum(rr):>+10.2f}")

    n = len(rs)
    se = (sum((r - sum(rs)/n) ** 2 for r in rs) / max(1, n - 1)) ** 0.5 / (n ** 0.5)
    print("\n" + "=" * 68)
    print(f"Standardfehler von R pro Trade: +/-{se:.4f} bei {n} Trades")
    print(f"  R pro Trade = {sum(rs)/n:+.4f}  ->  Bereich "
          f"{sum(rs)/n - 2*se:+.4f} bis {sum(rs)/n + 2*se:+.4f}")
    if abs(sum(rs)/n) < 2 * se:
        print("  Das Ergebnis ist von null NICHT unterscheidbar. Zu wenige Trades.")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
